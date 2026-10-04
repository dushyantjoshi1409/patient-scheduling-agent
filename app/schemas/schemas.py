from pydantic import BaseModel
from datetime import date, time, datetime
from uuid import UUID


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    response: str
    session_id: str


class DoctorOut(BaseModel):
    id: UUID
    name: str
    specialty: str
    bio: str

    model_config = {"from_attributes": True}


class SlotOut(BaseModel):
    id: UUID
    doctor_id: UUID
    date: date
    start_time: time
    end_time: time
    is_available: bool

    model_config = {"from_attributes": True}


class AppointmentOut(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    slot_id: UUID
    reason: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalScenarioRequest(BaseModel):
    scenarios: list[str] | None = None
    prompt_version: str | None = None


class EvalRunOut(BaseModel):
    id: UUID
    prompt_version: str
    scenario_name: str
    scores: dict
    total_score: float
    passed: bool
    failure_analysis: str

    model_config = {"from_attributes": True}


class ImprovementResult(BaseModel):
    old_version: str
    new_version: str
    old_scores: dict[str, float]
    new_scores: dict[str, float]
    regressions: list[str]
    improvements: list[str]
