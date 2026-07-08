"""
E2E-Test-Hilfsendpunkte — nur aktiv, wenn E2E_TESTING=true gesetzt ist.
Ermöglicht Playwright-Tests, einen verifizierten Testnutzer ohne SMTP
anzulegen, und Hilfsfunktionen für reproduzierbare Testdaten.

Wird nur in docker-compose.test.yml (E2E_TESTING=true) gemounted — in der
Produktivinstanz (docker-compose.yml ohne diese Env-Var) ist der Router
schlicht nicht registriert.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.auth.security import create_access_token, hash_password
from app.database import get_db

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


class SetupUserPayload(BaseModel):
    email: str
    password: str


@router.post("/setup-user")
def setup_user(payload: SetupUserPayload, db: Session = Depends(get_db)):
    if not os.environ.get("E2E_TESTING"):
        raise HTTPException(404, "Nicht im E2E-Modus.")
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        user = models.User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user_id": user.id,
    }
