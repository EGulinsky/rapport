"""
Benutzerkonten: Registrierung mit E-Mail-Bestätigung per Code, Login,
Passwort-Reset per Code sowie Passwort-Änderung im eingeloggten Zustand.

POST /api/auth/register          — Konto anlegen, Bestätigungscode per E-Mail
POST /api/auth/verify-email      — Code prüfen, Konto aktivieren, JWT zurückgeben
POST /api/auth/login             — Login, JWT zurückgeben
POST /api/auth/forgot-password   — Reset-Code per E-Mail (immer 200, keine User-Enumeration)
POST /api/auth/reset-password    — Reset-Code prüfen, neues Passwort setzen
GET  /api/auth/me                — aktueller Nutzer (erfordert Login)
POST /api/auth/change-password   — Passwort ändern (erfordert Login)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
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
from app.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class VerifyEmailPayload(BaseModel):
    email: EmailStr
    code: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


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

    user = models.User(email=payload.email, password_hash=hash_password(payload.password), email_verified=False)
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

    _consume_code(db, user, payload.code, "verify_email")
    user.email_verified = True
    db.commit()

    return AuthTokenResponse(access_token=create_access_token(user.id))


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
    return UserResponse(id=current_user.id, email=current_user.email, email_verified=current_user.email_verified)


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
