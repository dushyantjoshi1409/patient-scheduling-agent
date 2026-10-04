"""Tool declarations and async implementations for the scheduling agent.

Defines 6 tools the scheduling agent can call via Groq's function calling:
- search_doctors: Find doctors by name or specialty
- check_availability: List open slots for a doctor on a date
- book_appointment: Reserve a slot for a patient
- cancel_appointment: Cancel an existing appointment
- reschedule_appointment: Move an appointment to a new slot
- get_appointment_details: Look up appointment info

TOOL_DECLARATIONS holds OpenAI-compatible function schemas passed to Groq.
TOOL_FUNCTIONS maps tool names to async implementations that query Postgres.
"""
import uuid
from datetime import date as _date, time, datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Doctor, Slot, Appointment, Patient, AppointmentStatus


TOOL_DECLARATIONS = [
    {
        "name": "search_doctors",
        "description": "Search for doctors by name or specialty. Use this when a patient asks about a specific doctor or type of doctor.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Doctor name or specialty to search for (e.g., 'Smith', 'cardiology', 'dermatology')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "check_availability",
        "description": "Check available appointment slots for a specific doctor on a given date.",
        "parameters": {
            "type": "object",
            "properties": {
                "doctor_id": {
                    "type": "string",
                    "description": "UUID of the doctor"
                },
                "date": {
                    "type": "string",
                    "description": "Date to check availability (YYYY-MM-DD format)"
                }
            },
            "required": ["doctor_id", "date"]
        }
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment for a patient. Requires slot_id, patient info, and reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "slot_id": {
                    "type": "string",
                    "description": "UUID of the available slot to book"
                },
                "patient_name": {
                    "type": "string",
                    "description": "Full name of the patient"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the appointment"
                }
            },
            "required": ["slot_id", "patient_name", "reason"]
        }
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "string",
                    "description": "UUID of the appointment to cancel"
                }
            },
            "required": ["appointment_id"]
        }
    },
    {
        "name": "reschedule_appointment",
        "description": "Reschedule an existing appointment to a new slot.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "string",
                    "description": "UUID of the appointment to reschedule"
                },
                "new_slot_id": {
                    "type": "string",
                    "description": "UUID of the new slot"
                }
            },
            "required": ["appointment_id", "new_slot_id"]
        }
    },
    {
        "name": "get_appointment_details",
        "description": "Get details of an existing appointment by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "string",
                    "description": "UUID of the appointment"
                }
            },
            "required": ["appointment_id"]
        }
    },
]


async def search_doctors(db: AsyncSession, query: str) -> str:
    """Search doctors by name or specialty. Returns formatted list with IDs."""
    q = query.lower()
    result = await db.execute(select(Doctor))
    doctors = result.scalars().all()
    matches = [d for d in doctors if q in d.name.lower() or q in d.specialty.lower()]

    if not matches:
        return f"No doctors found matching '{query}'. Available specialties: {', '.join(set(d.specialty for d in doctors))}"

    lines = []
    for d in matches:
        lines.append(f"- {d.name} (ID: {d.id}) — {d.specialty}: {d.bio}")
    return "Found doctors:\n" + "\n".join(lines)


async def check_availability(db: AsyncSession, doctor_id: str, date: str = "", **kwargs) -> str:
    """Check available slots for a doctor on a given date. Suggests nearby dates if none found."""
    date_str = date or kwargs.get("date_str", "")
    try:
        doc_uuid = uuid.UUID(doctor_id)
        check_date = _date.fromisoformat(date_str)
    except ValueError:
        return "Invalid doctor_id or date format. Use UUID and YYYY-MM-DD."

    doctor = await db.get(Doctor, doc_uuid)
    if not doctor:
        return f"Doctor with ID {doctor_id} not found."

    result = await db.execute(
        select(Slot).where(
            and_(Slot.doctor_id == doc_uuid, Slot.date == check_date, Slot.is_available == True)
        ).order_by(Slot.start_time)
    )
    slots = result.scalars().all()

    if not slots:
        nearby = await db.execute(
            select(Slot.date).where(
                and_(Slot.doctor_id == doc_uuid, Slot.is_available == True, Slot.date > check_date)
            ).distinct().order_by(Slot.date).limit(3)
        )
        nearby_dates = [str(r[0]) for r in nearby.all()]
        msg = f"No available slots for {doctor.name} on {date_str}."
        if nearby_dates:
            msg += f" Next available dates: {', '.join(nearby_dates)}"
        return msg

    lines = [f"Available slots for {doctor.name} on {date_str}:"]
    for s in slots:
        lines.append(f"- {s.start_time.strftime('%I:%M %p')} to {s.end_time.strftime('%I:%M %p')} (Slot ID: {s.id})")
    return "\n".join(lines)


async def book_appointment(db: AsyncSession, slot_id: str, patient_name: str, reason: str, session_id: str) -> str:
    """Book an appointment: creates patient if needed, reserves the slot, returns confirmation."""
    try:
        slot_uuid = uuid.UUID(slot_id)
    except ValueError:
        return "Invalid slot_id format."

    slot = await db.get(Slot, slot_uuid)
    if not slot:
        return "Slot not found."
    if not slot.is_available:
        return "This slot is no longer available. Please check availability again."

    result = await db.execute(select(Patient).where(Patient.session_id == session_id))
    patient = result.scalar_one_or_none()
    if not patient:
        patient = Patient(id=uuid.uuid4(), session_id=session_id, name=patient_name)
        db.add(patient)
        await db.flush()
    elif patient_name and patient.name != patient_name:
        patient.name = patient_name

    doctor = await db.get(Doctor, slot.doctor_id)

    appointment = Appointment(
        id=uuid.uuid4(),
        patient_id=patient.id,
        doctor_id=slot.doctor_id,
        slot_id=slot.id,
        reason=reason,
        status=AppointmentStatus.SCHEDULED,
    )
    slot.is_available = False
    db.add(appointment)
    await db.commit()

    return (
        f"Appointment booked successfully!\n"
        f"- Appointment ID: {appointment.id}\n"
        f"- Doctor: {doctor.name}\n"
        f"- Date: {slot.date}\n"
        f"- Time: {slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}\n"
        f"- Reason: {reason}\n"
        f"- Patient: {patient_name}"
    )


async def cancel_appointment(db: AsyncSession, appointment_id: str) -> str:
    """Cancel an appointment and re-open its slot for others."""
    try:
        appt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        return "Invalid appointment_id format."

    appointment = await db.get(Appointment, appt_uuid)
    if not appointment:
        return f"Appointment {appointment_id} not found."
    if appointment.status == AppointmentStatus.CANCELLED:
        return "This appointment is already cancelled."

    appointment.status = AppointmentStatus.CANCELLED
    slot = await db.get(Slot, appointment.slot_id)
    if slot:
        slot.is_available = True

    await db.commit()
    return f"Appointment {appointment_id} has been cancelled. The slot is now available for others."


async def reschedule_appointment(db: AsyncSession, appointment_id: str, new_slot_id: str) -> str:
    """Move an appointment to a new slot: frees the old slot, reserves the new one."""
    try:
        appt_uuid = uuid.UUID(appointment_id)
        new_slot_uuid = uuid.UUID(new_slot_id)
    except ValueError:
        return "Invalid appointment_id or new_slot_id format."

    appointment = await db.get(Appointment, appt_uuid)
    if not appointment:
        return f"Appointment {appointment_id} not found."

    new_slot = await db.get(Slot, new_slot_uuid)
    if not new_slot:
        return "New slot not found."
    if not new_slot.is_available:
        return "The new slot is no longer available."

    old_slot = await db.get(Slot, appointment.slot_id)
    if old_slot:
        old_slot.is_available = True

    appointment.slot_id = new_slot.id
    appointment.doctor_id = new_slot.doctor_id
    new_slot.is_available = False

    doctor = await db.get(Doctor, new_slot.doctor_id)
    await db.commit()

    return (
        f"Appointment rescheduled successfully!\n"
        f"- Appointment ID: {appointment.id}\n"
        f"- Doctor: {doctor.name}\n"
        f"- New Date: {new_slot.date}\n"
        f"- New Time: {new_slot.start_time.strftime('%I:%M %p')} - {new_slot.end_time.strftime('%I:%M %p')}"
    )


async def get_appointment_details(db: AsyncSession, appointment_id: str) -> str:
    """Look up full details of an existing appointment by ID."""
    try:
        appt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        return "Invalid appointment_id format."

    appointment = await db.get(Appointment, appt_uuid)
    if not appointment:
        return f"Appointment {appointment_id} not found."

    doctor = await db.get(Doctor, appointment.doctor_id)
    slot = await db.get(Slot, appointment.slot_id)
    patient = await db.get(Patient, appointment.patient_id)

    return (
        f"Appointment Details:\n"
        f"- ID: {appointment.id}\n"
        f"- Status: {appointment.status.value}\n"
        f"- Doctor: {doctor.name} ({doctor.specialty})\n"
        f"- Date: {slot.date}\n"
        f"- Time: {slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}\n"
        f"- Patient: {patient.name}\n"
        f"- Reason: {appointment.reason}"
    )


TOOL_FUNCTIONS = {
    "search_doctors": search_doctors,
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "cancel_appointment": cancel_appointment,
    "reschedule_appointment": reschedule_appointment,
    "get_appointment_details": get_appointment_details,
}
