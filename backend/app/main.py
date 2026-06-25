import asyncio
import logging
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import (
    applications, import_excel, contacts, export_excel, export_pdf, settings,
    sync_google, sync_icloud, sync_targeted, sync_linkedin, sync_files,
    review, cleanup, calendar, attachments, merge, audit_log, backup, jobsearch,
)

logger = logging.getLogger(__name__)

# Sources currently running in background (prevents duplicate concurrent runs)
_RUNNING_SOURCES: set[str] = set()

# Interval between background sync runs (minutes)
_BG_INTERVAL_MINUTES = 20


async def _run_source(name: str, coro_fn):
    """Run a sync coroutine, guarded against concurrent execution."""
    if name in _RUNNING_SOURCES:
        return
    _RUNNING_SOURCES.add(name)
    try:
        await coro_fn()
    except Exception as e:
        logger.warning("Background sync %s failed: %s", name, e)
    finally:
        _RUNNING_SOURCES.discard(name)


async def _background_sync_loop():
    """Run all enabled sync sources every _BG_INTERVAL_MINUTES minutes."""
    # Wait a bit after startup so the app is fully ready
    await asyncio.sleep(30)

    while True:
        try:
            from app.database import SessionLocal
            from app import models
            from app.routers.sync_google import _do_gmail, _do_gcal
            from app.routers.sync_icloud import (
                _do_icloud_mail, _do_icloud_cal,
                _do_icloud_notes, _do_icloud_reminders, _do_icloud_calls,
            )
            from app.routers.sync_files import _do_local_files

            db = SessionLocal()
            try:
                sync_cfg = db.query(models.SyncSettings).first()
                google_on  = not sync_cfg or sync_cfg.google_enabled
                icloud_on  = not sync_cfg or sync_cfg.icloud_enabled
            finally:
                db.close()

            tasks = []
            if google_on:
                if not sync_cfg or sync_cfg.gmail_enabled:
                    tasks.append(_run_source("gmail", _do_gmail))
                if not sync_cfg or sync_cfg.gcal_enabled:
                    tasks.append(_run_source("gcal", _do_gcal))
            if icloud_on:
                if not sync_cfg or sync_cfg.icloud_mail_enabled:
                    tasks.append(_run_source("icloud_mail", _do_icloud_mail))
                if not sync_cfg or sync_cfg.icloud_cal_enabled:
                    tasks.append(_run_source("icloud_cal", _do_icloud_cal))
                if not sync_cfg or sync_cfg.icloud_notes_enabled:
                    tasks.append(_run_source("icloud_notes", _do_icloud_notes))
                if not sync_cfg or sync_cfg.icloud_reminders_enabled:
                    tasks.append(_run_source("icloud_reminders", _do_icloud_reminders))
                if not sync_cfg or sync_cfg.icloud_calls_enabled:
                    tasks.append(_run_source("icloud_calls", _do_icloud_calls))
            if not sync_cfg or sync_cfg.files_enabled:
                tasks.append(_run_source("local_files", _do_local_files))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Backup: run if enabled and due
            try:
                from app.routers.backup import do_backup
                from app.database import SessionLocal
                from app import models as _models
                _db = SessionLocal()
                try:
                    _bcfg = _db.query(_models.BackupConfig).first()
                    if _bcfg and _bcfg.enabled and _bcfg.backup_folder:
                        from datetime import timedelta
                        due = (
                            _bcfg.last_backup is None
                            or (datetime.now(timezone.utc) - _bcfg.last_backup)
                            >= timedelta(hours=_bcfg.frequency_hours)
                        )
                        if due and "backup" not in _RUNNING_SOURCES:
                            _RUNNING_SOURCES.add("backup")
                            try:
                                await do_backup()
                            finally:
                                _RUNNING_SOURCES.discard("backup")
                finally:
                    _db.close()
            except Exception as e:
                logger.warning("Backup error: %s", e)

        except Exception as e:
            logger.warning("Background sync loop error: %s", e)

        await asyncio.sleep(_BG_INTERVAL_MINUTES * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(_background_sync_loop())
    yield


app = FastAPI(
    title="JobTracker API",
    description="Bewerbungs-Tracking API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications.router)
app.include_router(import_excel.router)
app.include_router(contacts.router)
app.include_router(export_excel.router)
app.include_router(export_pdf.router)
app.include_router(settings.router)
app.include_router(sync_google.router)
app.include_router(sync_icloud.router)
app.include_router(sync_targeted.router)
app.include_router(sync_linkedin.router)
app.include_router(sync_files.router)
app.include_router(review.router)
app.include_router(attachments.router)
app.include_router(cleanup.router)
app.include_router(calendar.router)
app.include_router(merge.router)
app.include_router(audit_log.router)
app.include_router(backup.router)
app.include_router(jobsearch.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/sync/schedule/status")
def schedule_status():
    """Return background scheduler info."""
    return {
        "interval_minutes": _BG_INTERVAL_MINUTES,
        "running_sources": list(_RUNNING_SOURCES),
    }
