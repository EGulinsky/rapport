from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarEvent(BaseModel):
    id: int
    application_id: int
    firma: str
    rolle: str
    main_status: str
    typ: str
    datum: str
    titel: Optional[str] = None
    notiz: Optional[str] = None
    autor: Optional[str] = None
    source: Optional[str] = None


@router.get("/events", response_model=List[CalendarEvent])
def get_calendar_events(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = (
        db.query(models.Event, models.Application)
        .join(models.Application, models.Event.application_id == models.Application.id)
        .filter(models.Event.datum.isnot(None))
        .filter(
            models.Event.source.in_(models.CALENDAR_SOURCES)
            | models.Event.typ.in_(models.CALENDAR_TYPEN)
        )
    )
    if from_date:
        q = q.filter(models.Event.datum >= from_date)
    if to_date:
        q = q.filter(models.Event.datum <= to_date)
    q = q.order_by(models.Event.datum)

    return [
        CalendarEvent(
            id=ev.id,
            application_id=app.id,
            firma=app.firma,
            rolle=app.rolle,
            main_status=app.main_status,
            typ=ev.typ,
            datum=str(ev.datum),
            titel=ev.titel,
            notiz=ev.notiz,
            autor=ev.autor,
            source=ev.source,
        )
        for ev, app in q.all()
    ]
