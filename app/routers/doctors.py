from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Doctor
from app.schemas.schemas import DoctorOut

router = APIRouter(prefix="/api", tags=["doctors"])


@router.get("/doctors", response_model=list[DoctorOut])
async def list_doctors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Doctor).order_by(Doctor.name))
    return result.scalars().all()
