"""Chat router — main conversation endpoint."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.schemas import ChatRequest, ChatResponse
from app.models.models import Conversation, PromptVersion
from app.agent.scheduling_agent import run_agent_turn

router = APIRouter(prefix="/api", tags=["chat"])


async def _get_latest_prompt(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(PromptVersion).order_by(PromptVersion.id.desc()).limit(1)
    )
    pv = result.scalar_one_or_none()
    return pv.system_prompt if pv else None


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).where(Conversation.session_id == req.session_id)
    )
    convo = result.scalar_one_or_none()
    if not convo:
        convo = Conversation(id=uuid.uuid4(), session_id=req.session_id, messages=[])
        db.add(convo)

    history = convo.messages or []
    system_prompt = await _get_latest_prompt(db)

    response_text, updated_history = await run_agent_turn(
        db=db,
        session_id=req.session_id,
        user_message=req.message,
        history=history,
        system_prompt_text=system_prompt,
    )

    convo.messages = updated_history
    await db.commit()

    return ChatResponse(response=response_text, session_id=req.session_id)


@router.delete("/chat/{session_id}")
async def clear_chat(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).where(Conversation.session_id == session_id)
    )
    convo = result.scalar_one_or_none()
    if convo:
        convo.messages = []
        await db.commit()
    return {"status": "cleared"}
