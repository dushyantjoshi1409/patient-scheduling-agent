"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db, async_session
from app.seed import seed_database
from app.routers import chat, doctors, appointments, eval


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        await seed_database(db)
    yield


app = FastAPI(title="City Health Clinic Scheduling Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(eval.router)

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
