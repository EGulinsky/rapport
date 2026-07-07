import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logger import setup_logging, get_logger
from app.database import init_db
from app.routers import (
    applications, import_excel, contacts, export_excel, export_pdf, settings,
    sync_google, sync_icloud, sync_targeted, sync_linkedin, sync_files,
    review, cleanup, calendar, attachments, merge, audit_log, backup,
    analytics, sync_company, companies, startup_check, geo, auth,
)

setup_logging()
logger = get_logger("app")

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
        logger.warning("Background sync {} failed: {}", name, e)
    finally:
        _RUNNING_SOURCES.discard(name)


async def _background_sync_loop():
    """Run all enabled sync sources every _BG_INTERVAL_MINUTES minutes.

    Läuft (Projektentscheidung zur Mandantentrennung) vorerst nur für das
    erste/einzige registrierte Konto — echte Mehrkonten-Hintergrundjobs
    (mehrere parallele Sync-Läufe, einer pro Konto) wären ein deutlich
    größerer Umbau und sind bewusst zurückgestellt. Die einzelnen _do_*-
    Sync-Funktionen selbst laufen noch ungescoped (eigene SessionLocal()-
    Instanzen) — das ist der nächste Schritt der Mandantentrennung.
    """
    # Wait a bit after startup so the app is fully ready
    await asyncio.sleep(30)

    while True:
        try:
            from app.database import SessionLocal, set_session_user, get_first_user_id
            from app import models
            from app.routers.sync_google import _do_gmail, _do_gcal
            from app.routers.sync_icloud import (
                _do_icloud_mail, _do_icloud_cal,
                _do_icloud_notes, _do_icloud_reminders, _do_icloud_calls,
            )
            from app.routers.sync_files import _do_local_files

            db = SessionLocal()
            try:
                user_id = get_first_user_id(db)
                if user_id is None:
                    sync_cfg = None
                    google_on = icloud_on = False
                else:
                    set_session_user(db, user_id)
                    sync_cfg = db.query(models.SyncSettings).first()
                    google_on  = not sync_cfg or sync_cfg.google_enabled
                    icloud_on  = not sync_cfg or sync_cfg.icloud_enabled
            finally:
                db.close()

            if user_id is None:
                # Noch niemand registriert — Hintergrund-Sync macht ohne Konto
                # keinen Sinn (siehe Docstring). Trotzdem schlafen statt busy-loopen.
                await asyncio.sleep(_BG_INTERVAL_MINUTES * 60)
                continue

            tasks = []
            if google_on:
                if not sync_cfg or sync_cfg.gmail_enabled:
                    tasks.append(_run_source("gmail", lambda: _do_gmail(user_id)))
                if not sync_cfg or sync_cfg.gcal_enabled:
                    tasks.append(_run_source("gcal", lambda: _do_gcal(user_id)))
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
                tasks.append(_run_source("local_files", lambda: _do_local_files(user_id)))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Backup: run if enabled and due. Läuft (wie der gesamte Hintergrund-
            # Sync-Loop, siehe Docstring oben) vorerst nur für das erste/einzige
            # registrierte Konto — echte Mehrkonten-Hintergrundjobs sind ein
            # separater, größerer Umbau.
            try:
                from app.routers.backup import do_backup
                from app import models as _models
                _db = SessionLocal()
                try:
                    set_session_user(_db, user_id)
                    _bcfg = _db.query(_models.BackupConfig).first()
                    if _bcfg and _bcfg.enabled and _bcfg.backup_folder:
                        from datetime import timedelta
                        _last = _bcfg.last_backup
                        if _last is not None and _last.tzinfo is None:
                            _last = _last.replace(tzinfo=timezone.utc)
                        due = (
                            _last is None
                            or (datetime.now(timezone.utc) - _last)
                            >= timedelta(hours=_bcfg.frequency_hours)
                        )
                        if due and "backup" not in _RUNNING_SOURCES:
                            _RUNNING_SOURCES.add("backup")
                            try:
                                await do_backup(user_id)
                            finally:
                                _RUNNING_SOURCES.discard("backup")
                finally:
                    _db.close()
            except Exception as e:
                logger.warning("Backup error: {}", e)

        except Exception as e:
            logger.warning("Background sync loop error: {}", e)

        await asyncio.sleep(_BG_INTERVAL_MINUTES * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _auto_link_contacts()
    asyncio.create_task(_background_sync_loop())
    yield


def _auto_link_contacts():
    from app.database import SessionLocal
    from app.dedup import norm_firma
    from app import models as m
    from app.models import CompanyProfile
    try:
        with SessionLocal() as db:
            contacts = db.query(m.Contact).filter(m.Contact.company_profile_id.is_(None), m.Contact.firma.isnot(None)).all()
            for c in contacts:
                nname = norm_firma(c.firma)
                profile = db.query(CompanyProfile).filter(CompanyProfile.name_norm == nname).first()
                if profile:
                    c.company_profile_id = profile.id
            db.commit()
    except Exception as e:
        logger.warning("Auto link contacts failed: {}", e)


app = FastAPI(
    title="rapport API",
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

app.include_router(auth.router)
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
app.include_router(analytics.router)
app.include_router(sync_company.router)
app.include_router(companies.router)
app.include_router(startup_check.router)
app.include_router(geo.router)


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
