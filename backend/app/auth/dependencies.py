"""
FastAPI-Dependency zur Ermittlung des eingeloggten Nutzers aus dem
`Authorization: Bearer <jwt>`-Header. Wird von jedem geschützten Router als
`current_user: models.User = Depends(get_current_user)` eingebunden.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.auth.security import decode_access_token
from app.database import get_db


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Ungültiges oder abgelaufenes Token.")

    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Konto nicht gefunden.")
    return user
