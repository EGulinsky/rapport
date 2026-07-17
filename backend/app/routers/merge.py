from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.audit import add_audit
from app.auth.dependencies import get_current_user
from app.error_keys import ErrorKey, api_error

router = APIRouter(prefix="/api/merge", tags=["merge"])

MERGEABLE_APP_FIELDS = {
    "firma", "rolle", "main_status", "sub_status", "is_headhunter",
    "zielfirma_bei_hh", "quelle", "wurde_besetzt_von", "datum_bewerbung",
    "letztes_update", "kommentar", "stellenanzeige_url",
    "gespraech_1", "gespraech_2", "gespraech_3", "gespraech_4", "gespraech_5",
}

MERGEABLE_CONTACT_FIELDS = {
    "name", "email", "linkedin_url", "foto_url",
    "firma", "rolle", "typ", "notizen", "letzter_kontakt",
}


class MergeRequest(BaseModel):
    winner_id: int
    loser_ids: list[int]
    field_overrides: dict[str, int]  # field_name → source entity id


@router.post("/applications")
def merge_applications(
    req: MergeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not req.loser_ids:
        raise api_error(400, ErrorKey.MERGE_MIN_LOSER_REQUIRED, "Mindestens ein weiterer Eintrag erforderlich")
    if req.winner_id in req.loser_ids:
        raise api_error(400, ErrorKey.MERGE_WINNER_EQUALS_LOSER, "Der Gewinner kann nicht gleichzeitig Verlierer sein")
    all_ids = [req.winner_id] + req.loser_ids
    apps = {a.id: a for a in db.query(models.Application).filter(models.Application.id.in_(all_ids)).all()}
    if len(apps) != len(all_ids):
        raise api_error(404, ErrorKey.MERGE_APPLICATIONS_NOT_FOUND, "Eine oder mehrere Bewerbungen nicht gefunden")

    winner = apps[req.winner_id]
    losers = [apps[i] for i in req.loser_ids if i in apps]

    # Apply field overrides to winner, logging every changed field
    old_values = {
        field: getattr(winner, field)
        for field in req.field_overrides
        if field in MERGEABLE_APP_FIELDS
    }
    for field, source_id in req.field_overrides.items():
        if field in MERGEABLE_APP_FIELDS and source_id in apps:
            setattr(winner, field, getattr(apps[source_id], field))
    for field, old_v in old_values.items():
        new_v = getattr(winner, field)
        if str(old_v or "") != str(new_v or ""):
            is_status = field == "main_status"
            add_audit(db, "status_change" if is_status else "update", "user", app_id=winner.id,
                      field=field, old_value=old_v, new_value=new_v,
                      reason_key="merge_status_taken" if is_status else "merge_field_taken",
                      user_id=current_user.id)

    for loser in losers:
        # Store alias so future syncs recognise the old identifiers
        db.add(models.MergeAlias(
            entity_type="application",
            canonical_id=winner.id,
            alias_firma=loser.firma,
            alias_rolle=loser.rolle,
            alias_li_job_id=loser.linkedin_job_id,
            user_id=current_user.id,
        ))

        # Move events from loser to winner via the relationship attribute, not the
        # raw FK column: Application.events has cascade="all, delete-orphan", so
        # setting only event.application_id leaves loser's in-memory events
        # collection stale — the later db.delete(loser) then still treats these
        # events as belonging to loser and cascade-deletes them instead of moving
        # them to winner (live-reproduced bug, caught by tests).
        for event in list(loser.events):
            event.application = winner
        db.flush()

        # Move contacts (M2M, dedup)
        for contact in list(loser.contacts):
            if contact not in winner.contacts:
                winner.contacts.append(contact)

        # Reassign pending matches. Bulk .update() bypasses den zentralen
        # Mandanten-Filter, daher explizit auf user_id gefiltert (loser.id ist
        # bereits als current_user gehörend verifiziert, siehe apps-Lookup oben).
        db.query(models.PendingMatch).filter(
            models.PendingMatch.suggested_app_id == loser.id,
            models.PendingMatch.user_id == current_user.id,
        ).update({"suggested_app_id": winner.id})

        add_audit(db, "merge", "user", app_id=winner.id,
                  old_value=f"{loser.firma} – {loser.rolle} (#{loser.id})",
                  new_value=f"{winner.firma} – {winner.rolle} (#{winner.id})",
                  reason_key="merged", user_id=current_user.id)
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
def merge_companies(
    req: SimpleMergeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not req.loser_ids:
        raise api_error(400, ErrorKey.MERGE_MIN_LOSER_REQUIRED, "Mindestens ein weiterer Eintrag erforderlich")
    if req.winner_id in req.loser_ids:
        raise api_error(400, ErrorKey.MERGE_WINNER_EQUALS_LOSER, "Der Gewinner kann nicht gleichzeitig Verlierer sein")
    all_ids = [req.winner_id] + req.loser_ids
    companies = {c.id: c for c in db.query(models.CompanyProfile).filter(models.CompanyProfile.id.in_(all_ids)).all()}
    if len(companies) != len(all_ids):
        raise api_error(404, ErrorKey.MERGE_COMPANIES_NOT_FOUND, "Eine oder mehrere Firmen nicht gefunden")

    winner = companies[req.winner_id]
    losers = [companies[i] for i in req.loser_ids if i in companies]

    old_values = {
        field: getattr(winner, field)
        for field in req.field_overrides
        if field in MERGEABLE_COMPANY_FIELDS
    }
    for field, source_id in req.field_overrides.items():
        if field in MERGEABLE_COMPANY_FIELDS and source_id in companies:
            setattr(winner, field, getattr(companies[source_id], field))
    for field, old_v in old_values.items():
        new_v = getattr(winner, field)
        if str(old_v or "") != str(new_v or ""):
            add_audit(db, "update", "user", company_profile_id=winner.id,
                      field=field, old_value=old_v, new_value=new_v,
                      reason_key="merge_field_taken", user_id=current_user.id)

    winner_name = winner.name_display or winner.name_norm

    for loser in losers:
        # Reassign via the relationship attribute (not the raw FK column): setting
        # only company_profile_id leaves loser's in-memory relationship collections
        # (applications/hh_applications/direct_contacts) stale, so the subsequent
        # db.delete(loser) still treats these children as belonging to loser and
        # nulls their FK back out on commit — silently undoing the reassignment
        # (live-reproduced bug, caught by tests, never shipped as a live incident).
        for app in list(loser.applications):
            old_firma = app.firma
            app.company_profile = winner
            app.firma = winner_name
            if str(old_firma or "") != str(winner_name or ""):
                add_audit(db, "update", "user", app_id=app.id,
                          field="firma", old_value=old_firma, new_value=winner_name,
                          reason_key="companies_merged", user_id=current_user.id)
        for app in list(loser.hh_applications):
            old_ziel = app.zielfirma_bei_hh
            app.target_company_profile = winner
            if app.zielfirma_bei_hh:
                app.zielfirma_bei_hh = winner_name
                if str(old_ziel or "") != str(winner_name or ""):
                    add_audit(db, "update", "user", app_id=app.id,
                              field="zielfirma_bei_hh", old_value=old_ziel, new_value=winner_name,
                              reason_key="companies_merged", user_id=current_user.id)
        for contact in list(loser.direct_contacts):
            old_firma = contact.firma
            contact.company_profile = winner
            contact.firma = winner_name
            if str(old_firma or "") != str(winner_name or ""):
                add_audit(db, "update", "user", contact_id=contact.id,
                          field="firma", old_value=old_firma, new_value=winner_name,
                          reason_key="companies_merged", user_id=current_user.id)
        db.flush()

        add_audit(db, "merge", "user", company_profile_id=winner.id,
                  old_value=f"{loser.name_display or loser.name_norm} (#{loser.id})",
                  new_value=f"{winner.name_display or winner.name_norm} (#{winner.id})",
                  reason_key="companies_merged", user_id=current_user.id)
        db.delete(loser)

    db.commit()
    return {"success": True, "winner_id": winner.id}


@router.post("/contacts")
def merge_contacts(
    req: MergeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not req.loser_ids:
        raise api_error(400, ErrorKey.MERGE_MIN_LOSER_REQUIRED, "Mindestens ein weiterer Eintrag erforderlich")
    if req.winner_id in req.loser_ids:
        raise api_error(400, ErrorKey.MERGE_WINNER_EQUALS_LOSER, "Der Gewinner kann nicht gleichzeitig Verlierer sein")
    all_ids = [req.winner_id] + req.loser_ids
    contacts_map = {c.id: c for c in db.query(models.Contact).filter(models.Contact.id.in_(all_ids)).all()}
    if len(contacts_map) != len(all_ids):
        raise api_error(404, ErrorKey.MERGE_CONTACTS_NOT_FOUND, "Eine oder mehrere Kontakte nicht gefunden")

    winner = contacts_map[req.winner_id]
    losers = [contacts_map[i] for i in req.loser_ids if i in contacts_map]

    # Apply field overrides to winner, logging every changed field
    old_values = {
        field: getattr(winner, field)
        for field in req.field_overrides
        if field in MERGEABLE_CONTACT_FIELDS
    }
    for field, source_id in req.field_overrides.items():
        if field in MERGEABLE_CONTACT_FIELDS and source_id in contacts_map:
            setattr(winner, field, getattr(contacts_map[source_id], field))
    for field, old_v in old_values.items():
        new_v = getattr(winner, field)
        if str(old_v or "") != str(new_v or ""):
            add_audit(db, "update", "user", contact_id=winner.id,
                      field=field, old_value=old_v, new_value=new_v,
                      reason_key="merge_field_taken", user_id=current_user.id)

    from app.routers.sync_icloud import _normalize_phone

    for loser in losers:
        db.add(models.MergeAlias(
            entity_type="contact",
            canonical_id=winner.id,
            alias_name=loser.name,
            alias_email=loser.email,
            user_id=current_user.id,
        ))

        # Move application links (M2M, dedup)
        for app in list(loser.applications):
            if app not in winner.applications:
                winner.applications.append(app)

        # Union phone numbers onto the winner (dedup by normalized number) —
        # unlike the scalar MERGEABLE_CONTACT_FIELDS, phones aren't a
        # pick-one-side field, so both sides' numbers are combined.
        winner_norms = {_normalize_phone(p.number) for p in winner.phones}
        for phone in list(loser.phones):
            norm = _normalize_phone(phone.number)
            if norm and norm not in winner_norms:
                loser.phones.remove(phone)
                winner.phones.append(phone)
                winner_norms.add(norm)

        add_audit(db, "merge", "user", contact_id=winner.id,
                  old_value=f"{loser.name} (#{loser.id})",
                  new_value=f"{winner.name} (#{winner.id})",
                  reason_key="merged", user_id=current_user.id)
        db.delete(loser)

    db.commit()
    return {"success": True, "winner_id": winner.id}
