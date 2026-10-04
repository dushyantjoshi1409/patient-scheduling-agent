from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Appointment, Patient, Doctor, Slot, Conversation, EvalRun, PromptVersion
from app.schemas.schemas import AppointmentOut

router = APIRouter(prefix="/api", tags=["appointments"])


@router.get("/appointments/{session_id}", response_model=list[AppointmentOut])
async def list_appointments(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient).where(Patient.session_id == session_id))
    patient = result.scalar_one_or_none()
    if not patient:
        return []
    result = await db.execute(
        select(Appointment).where(Appointment.patient_id == patient.id).order_by(Appointment.created_at.desc())
    )
    return result.scalars().all()


@router.get("/admin/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)):
    doctors = (await db.execute(select(func.count(Doctor.id)))).scalar()
    patients = (await db.execute(select(func.count(Patient.id)))).scalar()
    appointments = (await db.execute(select(func.count(Appointment.id)))).scalar()
    conversations = (await db.execute(select(func.count(Conversation.id)))).scalar()
    eval_runs = (await db.execute(select(func.count(EvalRun.id)))).scalar()
    prompt_versions = (await db.execute(select(func.count(PromptVersion.id)))).scalar()
    return {
        "doctors": doctors, "patients": patients, "appointments": appointments,
        "conversations": conversations, "eval_runs": eval_runs, "prompt_versions": prompt_versions,
    }


@router.get("/admin/appointments")
async def admin_all_appointments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Appointment, Patient.name.label("patient_name"), Patient.session_id,
               Doctor.name.label("doctor_name"), Doctor.specialty,
               Slot.date, Slot.start_time, Slot.end_time)
        .join(Patient, Appointment.patient_id == Patient.id)
        .join(Doctor, Appointment.doctor_id == Doctor.id)
        .join(Slot, Appointment.slot_id == Slot.id)
        .order_by(Appointment.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": str(r.Appointment.id),
            "patient_name": r.patient_name or "Unknown",
            "session_id": r.session_id,
            "doctor_name": r.doctor_name,
            "specialty": r.specialty,
            "date": r.date.isoformat(),
            "start_time": r.start_time.strftime("%H:%M"),
            "end_time": r.end_time.strftime("%H:%M"),
            "reason": r.Appointment.reason,
            "status": r.Appointment.status.value if hasattr(r.Appointment.status, 'value') else r.Appointment.status,
            "created_at": r.Appointment.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/admin/eval-runs")
async def admin_eval_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EvalRun).order_by(EvalRun.created_at.desc()).limit(50)
    )
    runs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "prompt_version": r.prompt_version,
            "scenario_name": r.scenario_name,
            "scores": r.scores,
            "total_score": r.total_score,
            "passed": r.passed,
            "failure_analysis": r.failure_analysis,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/admin/prompt-versions")
async def admin_prompt_versions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptVersion).order_by(PromptVersion.id.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "change_description": r.change_description,
            "prompt_length": len(r.system_prompt),
            "created_at": r.created_at.isoformat(),
        }
        for r in versions
    ]
