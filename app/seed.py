"""Seed the database with doctors and time slots for the next 14 days."""
import uuid
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Doctor, Slot, PromptVersion
from app.agent.prompts import SYSTEM_PROMPT_V1

DOCTORS = [
    {"name": "Dr. Sarah Smith", "specialty": "General Practice", "bio": "Board-certified family medicine physician with 12 years of experience."},
    {"name": "Dr. James Wilson", "specialty": "Cardiology", "bio": "Interventional cardiologist specializing in preventive heart care."},
    {"name": "Dr. Emily Chen", "specialty": "Dermatology", "bio": "Dermatologist focused on medical and cosmetic skin conditions."},
    {"name": "Dr. Michael Brown", "specialty": "Orthopedics", "bio": "Sports medicine specialist with expertise in joint and bone care."},
    {"name": "Dr. Lisa Patel", "specialty": "Pediatrics", "bio": "Pediatrician passionate about child wellness and development."},
]

SLOT_TIMES = [
    (time(9, 0), time(9, 30)),
    (time(9, 30), time(10, 0)),
    (time(10, 0), time(10, 30)),
    (time(10, 30), time(11, 0)),
    (time(11, 0), time(11, 30)),
    (time(14, 0), time(14, 30)),
    (time(14, 30), time(15, 0)),
    (time(15, 0), time(15, 30)),
    (time(15, 30), time(16, 0)),
    (time(16, 0), time(16, 30)),
]


async def seed_database(db: AsyncSession):
    existing = await db.execute(select(Doctor).limit(1))
    if existing.scalar_one_or_none():
        return

    doctors = []
    for doc_data in DOCTORS:
        doctor = Doctor(id=uuid.uuid4(), **doc_data)
        db.add(doctor)
        doctors.append(doctor)

    await db.flush()

    today = date.today()
    for doctor in doctors:
        for day_offset in range(1, 15):
            slot_date = today + timedelta(days=day_offset)
            if slot_date.weekday() >= 5:
                continue
            for start, end in SLOT_TIMES:
                slot = Slot(
                    id=uuid.uuid4(),
                    doctor_id=doctor.id,
                    date=slot_date,
                    start_time=start,
                    end_time=end,
                    is_available=True,
                )
                db.add(slot)

    existing_prompt = await db.execute(select(PromptVersion).where(PromptVersion.version == "v1"))
    if not existing_prompt.scalar_one_or_none():
        prompt_v1 = PromptVersion(
            version="v1",
            system_prompt=SYSTEM_PROMPT_V1,
            change_description="Initial system prompt",
        )
        db.add(prompt_v1)

    await db.commit()
