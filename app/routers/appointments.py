from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Appointment
from app.schemas.schemas import AppointmentOut

router = APIRouter(prefix="/api", tags=["appointments"])


@router.get("/appointments/{session_id}", response_model=list[AppointmentOut])
async def list_appointments(session_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.models import Patient
    result = await db.execute(select(Patient).where(Patient.session_id == session_id))
    patient = result.scalar_one_or_none()
    if not patient:
        return []
    result = await db.execute(
        select(Appointment).where(Appointment.patient_id == patient.id).order_by(Appointment.created_at.desc())
    )
    return result.scalars().all()
