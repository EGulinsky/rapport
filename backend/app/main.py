from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import applications, import_excel, contacts, export_excel, settings, sync_google, sync_icloud, sync_targeted, sync_linkedin, review, cleanup, calendar


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="JobTracker API",
    description="Bewerbungs-Tracking API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: set to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications.router)
app.include_router(import_excel.router)
app.include_router(contacts.router)
app.include_router(export_excel.router)
app.include_router(settings.router)
app.include_router(sync_google.router)
app.include_router(sync_icloud.router)
app.include_router(sync_targeted.router)
app.include_router(sync_linkedin.router)
app.include_router(review.router)
app.include_router(cleanup.router)
app.include_router(calendar.router)


@app.get("/health")
def health():
    return {"status": "ok"}
