"""
Benutzerkonten: Registrierung mit E-Mail-Bestätigung per Code, Login,
Passwort-Reset per Code sowie Passwort-Änderung im eingeloggten Zustand.

POST /api/auth/register          — Konto anlegen, Bestätigungscode per E-Mail
POST /api/auth/verify-email      — Code prüfen, Konto aktivieren, JWT zurückgeben
POST /api/auth/resend-code       — neuen Bestätigungscode senden (unverifiziertes Konto)
POST /api/auth/login             — Login, JWT zurückgeben
POST /api/auth/forgot-password   — Reset-Code per E-Mail (immer 200, keine User-Enumeration)
POST /api/auth/reset-password    — Reset-Code prüfen, neues Passwort setzen
GET  /api/auth/me                — aktueller Nutzer (erfordert Login)
POST /api/auth/change-password   — Passwort ändern (erfordert Login)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app import models
from app.auth.dependencies import get_current_user
from app.auth.email import EmailNotConfigured, send_verification_code
from app.auth.security import (
    create_access_token,
    generate_verification_code,
    hash_password,
    verify_password,
    verification_code_expiry,
)
from app.database import DATABASE_URL, claim_unowned_data, get_db
from app.error_keys import ErrorKey, api_error

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_CV_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_CV_EXTENSIONS = {".pdf", ".doc", ".docx"}

_DB_DIR = os.path.dirname(DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", ""))
CV_ROOT = os.path.join(_DB_DIR, "user_files")


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    ui_language: str = Field(default="en", pattern="^(de|en)$")


class VerifyEmailPayload(BaseModel):
    email: EmailStr
    code: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class ResendCodePayload(BaseModel):
    email: EmailStr


class ForgotPasswordPayload(BaseModel):
    email: EmailStr


class ResetPasswordPayload(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(min_length=8)


class ChangePasswordPayload(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    email_verified: bool
    vorname: Optional[str] = None
    nachname: Optional[str] = None
    linkedin_url: Optional[str] = None
    cv_filename: Optional[str] = None
    cv_size_bytes: Optional[int] = None
    linkedin_profile_synced_at: Optional[datetime] = None
    ui_language: str = "de"
    home_location: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None


class ProfilePayload(BaseModel):
    vorname: Optional[str] = None
    nachname: Optional[str] = None
    linkedin_url: Optional[str] = None
    # Unconditional overwrite like vorname/nachname/linkedin_url -- but
    # update_profile() only re-geocodes when this actually changed, so an
    # unrelated profile save (e.g. just changing vorname) doesn't burn an
    # extra geocoding API call every time.
    home_location: Optional[str] = None
    # Optional und nur bei Angabe übernommen (siehe update_profile) — anders als
    # vorname/nachname/linkedin_url, die dieser Endpoint unconditional überschreibt.
    # Ein Profil-Save aus einem anderen Tab (z.B. CV-Upload) darf die Sprache nicht
    # unbeabsichtigt zurücksetzen, nur weil das Feld im Payload fehlt.
    ui_language: Optional[str] = None


def _user_response(user: models.User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        vorname=user.vorname,
        nachname=user.nachname,
        linkedin_url=user.linkedin_url,
        cv_filename=user.cv_filename,
        cv_size_bytes=user.cv_size_bytes,
        linkedin_profile_synced_at=user.linkedin_profile_synced_at,
        ui_language=user.ui_language,
        home_location=user.home_location,
        home_lat=user.home_lat,
        home_lng=user.home_lng,
    )


def _issue_code(db: Session, user: models.User, purpose: str) -> str:
    code = generate_verification_code()
    db.add(models.EmailVerificationCode(
        user_id=user.id, code=code, purpose=purpose, expires_at=verification_code_expiry(),
    ))
    db.commit()
    return code


def _consume_code(db: Session, user: models.User, code: str, purpose: str) -> models.EmailVerificationCode:
    entry = (
        db.query(models.EmailVerificationCode)
        .filter_by(user_id=user.id, code=code, purpose=purpose, used_at=None)
        .order_by(models.EmailVerificationCode.id.desc())
        .first()
    )
    if not entry:
        raise api_error(400, ErrorKey.AUTH_CODE_INVALID, "Code ungültig.")
    if entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise api_error(400, ErrorKey.AUTH_CODE_EXPIRED, "Code ist abgelaufen.")
    entry.used_at = datetime.now(timezone.utc)
    return entry


@router.post("/register", status_code=201)
def register(payload: RegisterPayload, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter_by(email=payload.email).first()
    if existing:
        raise api_error(409, ErrorKey.AUTH_EMAIL_ALREADY_REGISTERED, "Diese E-Mail-Adresse ist bereits registriert.")

    user = models.User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        email_verified=False,
        ui_language=payload.ui_language,
    )
    db.add(user)
    db.flush()

    code = _issue_code(db, user, "verify_email")
    try:
        send_verification_code(user.email, code, "verify_email", user.ui_language)
    except EmailNotConfigured as e:
        raise api_error(502, ErrorKey.AUTH_EMAIL_SEND_FAILED, str(e))

    return {"message": "Konto angelegt. Bitte den Bestätigungscode aus der E-Mail eingeben."}


@router.post("/verify-email", response_model=AuthTokenResponse)
def verify_email(payload: VerifyEmailPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        raise api_error(404, ErrorKey.AUTH_ACCOUNT_NOT_FOUND, "Konto nicht gefunden.")
    if user.email_verified:
        raise api_error(400, ErrorKey.AUTH_ALREADY_VERIFIED, "E-Mail-Adresse ist bereits bestätigt.")

    # Vor dem Markieren prüfen: ist dies das allererste je bestätigte Konto?
    # Falls ja, gehört diesem Konto der komplette bisherige (kontolose)
    # Datenbestand aus der Zeit vor den Benutzerkonten (siehe claim_unowned_data()).
    is_first_verified_ever = db.query(models.User).filter_by(email_verified=True).count() == 0

    _consume_code(db, user, payload.code, "verify_email")
    user.email_verified = True
    db.commit()

    if is_first_verified_ever:
        claim_unowned_data(db, user.id)

    return AuthTokenResponse(access_token=create_access_token(user.id))


@router.post("/resend-code")
def resend_code(payload: ResendCodePayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if user and not user.email_verified:
        code = _issue_code(db, user, "verify_email")
        try:
            send_verification_code(user.email, code, "verify_email", user.ui_language)
        except EmailNotConfigured as e:
            raise api_error(502, ErrorKey.AUTH_EMAIL_SEND_FAILED, str(e))
    # Immer dieselbe Antwort — verhindert Rückschlüsse auf registrierte/verifizierte
    # Adressen (User-Enumeration), analog zu forgot-password.
    return {"message": "Falls ein unbestätigtes Konto mit dieser E-Mail-Adresse existiert, wurde ein neuer Code gesendet."}


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise api_error(401, ErrorKey.AUTH_LOGIN_FAILED, "E-Mail oder Passwort ist falsch.")
    if not user.email_verified:
        raise api_error(403, ErrorKey.AUTH_EMAIL_NOT_VERIFIED, "E-Mail-Adresse ist noch nicht bestätigt.")

    return AuthTokenResponse(access_token=create_access_token(user.id))


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if user:
        code = _issue_code(db, user, "reset_password")
        try:
            send_verification_code(user.email, code, "reset_password", user.ui_language)
        except EmailNotConfigured as e:
            raise api_error(502, ErrorKey.AUTH_EMAIL_SEND_FAILED, str(e))
    # Immer dieselbe Antwort, unabhängig davon ob die E-Mail existiert — verhindert
    # Rückschlüsse auf registrierte Adressen (User-Enumeration).
    return {"message": "Falls ein Konto mit dieser E-Mail-Adresse existiert, wurde ein Code gesendet."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        raise api_error(400, ErrorKey.AUTH_CODE_INVALID, "Code ungültig.")

    _consume_code(db, user, payload.code, "reset_password")
    user.password_hash = hash_password(payload.new_password)
    db.commit()

    return {"message": "Passwort wurde zurückgesetzt."}


@router.get("/me", response_model=UserResponse)
def me(current_user: models.User = Depends(get_current_user)):
    return _user_response(current_user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordPayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.password_hash):
        raise api_error(401, ErrorKey.AUTH_CURRENT_PASSWORD_WRONG, "Aktuelles Passwort ist falsch.")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Passwort wurde geändert."}


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    payload: ProfilePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.vorname = payload.vorname
    current_user.nachname = payload.nachname
    current_user.linkedin_url = payload.linkedin_url

    if payload.home_location != current_user.home_location:
        current_user.home_location = payload.home_location
        if payload.home_location and payload.home_location.strip():
            from app.routers.geo import _get_maps_api_key, geocode_one
            api_key = _get_maps_api_key(db, current_user.id)
            coords = await geocode_one(payload.home_location, api_key)
            current_user.home_lat = coords[0] if coords else None
            current_user.home_lng = coords[1] if coords else None
        else:
            current_user.home_lat = None
            current_user.home_lng = None

    language_changed = payload.ui_language is not None and payload.ui_language != current_user.ui_language
    if payload.ui_language is not None:
        current_user.ui_language = payload.ui_language
    db.commit()
    db.refresh(current_user)

    if language_changed:
        from app.agent_client import agent_patch, get_agent_token
        if get_agent_token(db):
            try:
                await agent_patch(db, "/config", json={"ui_language": current_user.ui_language}, timeout=5)
            except Exception:
                pass  # agent may be offline — profile save must not fail because of this

    return _user_response(current_user)


@router.post("/cv", response_model=UserResponse, status_code=201)
async def upload_cv(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filename = file.filename or "lebenslauf"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_CV_EXTENSIONS:
        raise api_error(400, ErrorKey.AUTH_CV_TYPE_INVALID, "Nur PDF, DOC oder DOCX werden als Lebenslauf akzeptiert.")

    data = await file.read()
    if len(data) > MAX_CV_BYTES:
        raise api_error(413, ErrorKey.AUTH_CV_TOO_LARGE, "Datei ist größer als 15 MB.")

    if current_user.cv_storage_path:
        old_path = os.path.join(CV_ROOT, current_user.cv_storage_path)
        if os.path.exists(old_path):
            os.remove(old_path)

    target_dir = os.path.join(CV_ROOT, str(current_user.id))
    os.makedirs(target_dir, exist_ok=True)
    safe_name = os.path.basename(filename)
    target_path = os.path.join(target_dir, safe_name)
    with open(target_path, "wb") as f:
        f.write(data)

    current_user.cv_filename = safe_name
    current_user.cv_content_type = file.content_type
    current_user.cv_size_bytes = len(data)
    current_user.cv_storage_path = os.path.join(str(current_user.id), safe_name)

    # Extracted once here, at upload time, rather than per AI assessment —
    # see User.cv_extracted_text's docstring in models.py for why. Offloaded
    # to a thread since PDF/DOCX parsing is real, measurable CPU+I/O work
    # that would otherwise block this async endpoint's event loop.
    from app.cv_extract import extract_cv_text
    current_user.cv_extracted_text = await asyncio.to_thread(extract_cv_text, target_path)

    db.commit()
    db.refresh(current_user)
    return _user_response(current_user)


@router.get("/cv")
def download_cv(current_user: models.User = Depends(get_current_user)):
    if not current_user.cv_storage_path:
        raise api_error(404, ErrorKey.AUTH_NO_CV, "Kein Lebenslauf hinterlegt.")
    full_path = os.path.join(CV_ROOT, current_user.cv_storage_path)
    if not os.path.exists(full_path):
        raise api_error(404, ErrorKey.AUTH_CV_FILE_MISSING, "Datei nicht mehr vorhanden.")
    return FileResponse(
        full_path,
        media_type=current_user.cv_content_type or "application/octet-stream",
        filename=current_user.cv_filename,
    )


@router.delete("/cv", status_code=204)
def delete_cv(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.cv_storage_path:
        full_path = os.path.join(CV_ROOT, current_user.cv_storage_path)
        if os.path.exists(full_path):
            os.remove(full_path)
    current_user.cv_filename = None
    current_user.cv_content_type = None
    current_user.cv_size_bytes = None
    current_user.cv_storage_path = None
    current_user.cv_extracted_text = None
    db.commit()
