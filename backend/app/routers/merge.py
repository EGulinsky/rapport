from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.audit import add_audit

router = APIRouter(prefix="/api/merge", tags=["merge"])

MERGEABLE_APP_FIELDS = {
    "firma", "rolle", "main_status", "sub_status", "is_headhunter",
    "zielfirma_bei_hh", "quelle", "wurde_besetzt_von", "datum_bewerbung",
    "letztes_update", "kommentar", "stellenanzeige_url",
    "gespraech_1", "gespraech_2", "gespraech_3", "gespraech_4", "gespraech_5",
}

MERGEABLE_CONTACT_FIELDS = {
    "name", "email", "telefon", "linkedin_url", "foto_url",
    "firma", "rolle", "typ", "notizen", "letzter_kontakt",
}


class MergeRequest(BaseModel):
    winner_id: int
    loser_ids: list[int]
    field_overrides: dict[str, int]  # field_name → source entity id


@router.post("/applications")
def merge_applications(req: MergeRequest, db: Session = Depends(get_db)):
    if not req.loser_ids:
        raise HTTPException(400, "Mindestens ein weiterer Eintrag erforderlich")
    all_ids = [req.winner_id] + req.loser_ids
    apps = {a.id: a for a in db.query(models.Application).filter(models.Application.id.in_(all_ids)).all()}
    if len(apps) != len(all_ids):
        raise HTTPException(404, "Eine oder mehrere Bewerbungen nicht gefunden")

    winner = apps[req.winner_id]
    losers = [apps[i] for i in req.loser_ids if i in apps]

    # Apply field overrides to winner, logging status changes explicitly
    old_main = winner.main_status
    for field, source_id in req.field_overrides.items():
        if field in MERGEABLE_APP_FIELDS and source_id in apps:
            setattr(winner, field, getattr(apps[source_id], field))
    if winner.main_status != old_main:
        add_audit(db, "status_change", "user", app_id=winner.id,
                  field="main_status", old_value=old_main, new_value=winner.main_status,
                  reason="Zusammenführen: Status übernommen")

    for loser in losers:
        # Store alias so future syncs recognise the old identifiers
        db.add(models.MergeAlias(
            entity_type="application",
            canonical_id=winner.id,
            alias_firma=loser.firma,
            alias_rolle=loser.rolle,
            alias_li_job_id=loser.linkedin_job_id,
        ))

        # Move events from loser to winner
        for event in list(loser.events):
            event.application_id = winner.id
        db.flush()

        # Move contacts (M2M, dedup)
        for contact in list(loser.contacts):
            if contact not in winner.contacts:
                winner.contacts.append(contact)

        # Reassign pending matches
        db.query(models.PendingMatch).filter(
            models.PendingMatch.suggested_app_id == loser.id
        ).update({"suggested_app_id": winner.id})

        add_audit(db, "merge", "user", app_id=winner.id,
                  old_value=f"{loser.firma} – {loser.rolle} (#{loser.id})",
                  new_value=f"{winner.firma} – {winner.rolle} (#{winner.id})",
                  reason="Zusammengeführt")
        db.delete(loser)

    db.commit()
    return {"success": True, "winner_id": winner.id}


MERGEABLE_COMPANY_FIELDS = {
    "name_display", "industry", "company_type", "employee_range", "employee_count",
    "founded_year", "hq_city", "hq_country", "website", "linkedin_company_url", "description",
}


class SimpleMergeRequest(BaseModel):
    winner_id: int
    loser_ids: list[int]
    field_overrides: dict[str, int] = {}


@router.post("/companies")
def merge_companies(req: SimpleMergeRequest, db: Session = Depends(get_db)):
    if not req.loser_ids:
        raise HTTPException(400, "Mindestens ein weiterer Eintrag erforderlich")
    all_ids = [req.winner_id] + req.loser_ids
    companies = {c.id: c for c in db.query(models.CompanyProfile).filter(models.CompanyProfile.id.in_(all_ids)).all()}
    if len(companies) != len(all_ids):
        raise HTTPException(404, "Eine oder mehrere Firmen nicht gefunden")

    winner = companies[req.winner_id]
    losers = [companies[i] for i in req.loser_ids if i in companies]

    for field, source_id in req.field_overrides.items():
        if field in MERGEABLE_COMPANY_FIELDS and source_id in companies:
            setattr(winner, field, getattr(companies[source_id], field))

    winner_name = winner.name_display or winner.name_norm

    for loser in losers:
        for app in list(loser.applications):
            app.company_profile_id = winner.id
            app.firma = winner_name
        for app in list(loser.hh_applications):
            app.target_company_profile_id = winner.id
            if app.zielfirma_bei_hh:
                app.zielfirma_bei_hh = winner_name
        for contact in list(loser.direct_contacts):
            contact.company_profile_id = winner.id
            contact.firma = winner_name
        db.flush()

        add_audit(db, "merge", "user", app_id=None,
                  old_value=f"{loser.name_display or loser.name_norm} (#{loser.id})",
                  new_value=f"{winner.name_display or winner.name_norm} (#{winner.id})",
                  reason="Firmen zusammengeführt")
        db.delete(loser)

    db.commit()
    return {"success": True, "winner_id": winner.id}


@router.post("/contacts")
def merge_contacts(req: MergeRequest, db: Session = Depends(get_db)):
    if not req.loser_ids:
        raise HTTPException(400, "Mindestens ein weiterer Eintrag erforderlich")
    all_ids = [req.winner_id] + req.loser_ids
    contacts_map = {c.id: c for c in db.query(models.Contact).filter(models.Contact.id.in_(all_ids)).all()}
    if len(contacts_map) != len(all_ids):
        raise HTTPException(404, "Einen oder mehrere Kontakte nicht gefunden")

    winner = contacts_map[req.winner_id]
    losers = [contacts_map[i] for i in req.loser_ids if i in contacts_map]

    # Apply field overrides to winner
    for field, source_id in req.field_overrides.items():
        if field in MERGEABLE_CONTACT_FIELDS and source_id in contacts_map:
            setattr(winner, field, getattr(contacts_map[source_id], field))

    for loser in losers:
        db.add(models.MergeAlias(
            entity_type="contact",
            canonical_id=winner.id,
            alias_name=loser.name,
            alias_email=loser.email,
        ))

        # Move application links (M2M, dedup)
        for app in list(loser.applications):
            if app not in winner.applications:
                winner.applications.append(app)

        db.delete(loser)

    db.commit()
    return {"success": True, "winner_id": winner.id}
