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

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    ui_language: str = "de"


class ProfilePayload(BaseModel):
    vorname: Optional[str] = None
    nachname: Optional[str] = None
    linkedin_url: Optional[str] = None
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
        ui_language=user.ui_language,
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
        raise HTTPException(400, "Code ungültig.")
    if entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Code ist abgelaufen.")
    entry.used_at = datetime.now(timezone.utc)
    return entry


@router.post("/register", status_code=201)
def register(payload: RegisterPayload, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter_by(email=payload.email).first()
    if existing:
        raise HTTPException(409, "Diese E-Mail-Adresse ist bereits registriert.")

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
        send_verification_code(user.email, code, "verify_email")
    except EmailNotConfigured as e:
        raise HTTPException(502, str(e))

    return {"message": "Konto angelegt. Bitte den Bestätigungscode aus der E-Mail eingeben."}


@router.post("/verify-email", response_model=AuthTokenResponse)
def verify_email(payload: VerifyEmailPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        raise HTTPException(404, "Konto nicht gefunden.")
    if user.email_verified:
        raise HTTPException(400, "E-Mail-Adresse ist bereits bestätigt.")

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
            send_verification_code(user.email, code, "verify_email")
        except EmailNotConfigured as e:
            raise HTTPException(502, str(e))
    # Immer dieselbe Antwort — verhindert Rückschlüsse auf registrierte/verifizierte
    # Adressen (User-Enumeration), analog zu forgot-password.
    return {"message": "Falls ein unbestätigtes Konto mit dieser E-Mail-Adresse existiert, wurde ein neuer Code gesendet."}


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort ist falsch.")
    if not user.email_verified:
        raise HTTPException(403, "E-Mail-Adresse ist noch nicht bestätigt.")

    return AuthTokenResponse(access_token=create_access_token(user.id))


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if user:
        code = _issue_code(db, user, "reset_password")
        try:
            send_verification_code(user.email, code, "reset_password")
        except EmailNotConfigured as e:
            raise HTTPException(502, str(e))
    # Immer dieselbe Antwort, unabhängig davon ob die E-Mail existiert — verhindert
    # Rückschlüsse auf registrierte Adressen (User-Enumeration).
    return {"message": "Falls ein Konto mit dieser E-Mail-Adresse existiert, wurde ein Code gesendet."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordPayload, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        raise HTTPException(400, "Code ungültig.")

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
        raise HTTPException(401, "Aktuelles Passwort ist falsch.")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Passwort wurde geändert."}


@router.patch("/profile", response_model=UserResponse)
def update_profile(
    payload: ProfilePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.vorname = payload.vorname
    current_user.nachname = payload.nachname
    current_user.linkedin_url = payload.linkedin_url
    if payload.ui_language is not None:
        current_user.ui_language = payload.ui_language
    db.commit()
    db.refresh(current_user)
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
        raise HTTPException(400, "Nur PDF, DOC oder DOCX werden als Lebenslauf akzeptiert.")

    data = await file.read()
    if len(data) > MAX_CV_BYTES:
        raise HTTPException(413, "Datei ist größer als 15 MB.")

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
    db.commit()
    db.refresh(current_user)
    return _user_response(current_user)


@router.get("/cv")
def download_cv(current_user: models.User = Depends(get_current_user)):
    if not current_user.cv_storage_path:
        raise HTTPException(404, "Kein Lebenslauf hinterlegt.")
    full_path = os.path.join(CV_ROOT, current_user.cv_storage_path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Datei nicht mehr vorhanden.")
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
    db.commit()
