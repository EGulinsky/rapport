"""
Factories für synthetische Testdaten. Bewusst als einfache Funktionen (nicht
polyfactory-ModelFactory-Klassen) implementiert — vorhersagbares Verhalten bei
Unique-Constraints (CompanyProfile.name_norm) und Self-Referential-FKs
(parent_company_id) ist wichtiger als Boilerplate-Ersparnis.

Jede Factory: legt ein Objekt mit sinnvollen Zufallswerten an, flusht es in die
übergebene Session (damit .id direkt verfügbar ist) und gibt es zurück.
Alle Felder sind per Keyword-Argument überschreibbar — für Edge Cases gezielt
einzelne Felder setzen (z.B. company_profile_factory(db, website=None)).
"""
from __future__ import annotations

from datetime import date, timedelta

from faker import Faker
from sqlalchemy.orm import Session

from app import models

fake = Faker("de_DE")

# Muss mit conftest.py::DEFAULT_TEST_USER_ID übereinstimmen — der `client`-Fixture
# überschreibt get_current_user() mit einem Fake-Nutzer dieser ID, damit
# bestehende (nicht auth-bezogene) Tests ihre per Factory angelegten Daten
# weiterhin sehen, ohne dass jede einzelne Factory-Aufrufstelle angepasst
# werden muss. db_session-only-Tests (kein HTTP-Layer) aktivieren den
# Mandanten-Filter nie und sind von diesem Default unberührt.
_DEFAULT_TEST_USER_ID = 1


def application_factory(db: Session, **overrides) -> models.Application:
    defaults = dict(
        firma=fake.company(),
        rolle=fake.job(),
        main_status="applied",
        sub_status=None,
        is_headhunter=False,
        datum_bewerbung=date.today() - timedelta(days=fake.random_int(0, 60)),
        user_id=_DEFAULT_TEST_USER_ID,
    )
    defaults.update(overrides)
    app = models.Application(**defaults)
    db.add(app)
    db.flush()
    return app


def contact_factory(db: Session, **overrides) -> models.Contact:
    defaults = dict(
        name=fake.name(),
        email=fake.unique.email(),
        firma=fake.company(),
        typ="hr",
        user_id=_DEFAULT_TEST_USER_ID,
    )
    defaults.update(overrides)
    contact = models.Contact(**defaults)
    db.add(contact)
    db.flush()
    return contact


def company_profile_factory(db: Session, **overrides) -> models.CompanyProfile:
    name = overrides.pop("name_display", None) or fake.company()
    defaults = dict(
        name_norm=fake.unique.slug(),
        name_display=name,
        website=f"https://www.{fake.unique.domain_word()}.de/",
        sync_status="done",
        user_id=_DEFAULT_TEST_USER_ID,
    )
    defaults.update(overrides)
    profile = models.CompanyProfile(**defaults)
    db.add(profile)
    db.flush()
    return profile


def icloud_vcard(
    fn: str, family: str | None = None, given: str | None = None,
    email: str | None = None, org: str | None = None, title: str | None = None,
    tel: str | None = None, tel_type: str | None = None, linkedin_url: str | None = None,
) -> str:
    """Baut einen echten, über vobject serialisierten vCard-3.0-String für Tests
    des iCloud-CardDAV-Kontakte-Syncs (_parse_vcard/_sync_contacts_http)."""
    import vobject

    card = vobject.vCard()
    card.add("fn").value = fn
    if family:
        n = card.add("n")
        n.value = vobject.vcard.Name(family=family, given=given or "")
    if email:
        card.add("email").value = email
    if org:
        card.add("org").value = [org]
    if title:
        card.add("title").value = title
    if tel:
        tel_prop = card.add("tel")
        tel_prop.value = tel
        if tel_type:
            tel_prop.type_param = tel_type
    if linkedin_url:
        card.add("url").value = linkedin_url
    return card.serialize()


def event_factory(db: Session, application: models.Application, **overrides) -> models.Event:
    defaults = dict(
        application_id=application.id,
        typ="mail",
        datum=date.today() - timedelta(days=fake.random_int(0, 30)),
        titel=fake.sentence(nb_words=4),
        source="gmail",
        user_id=application.user_id,
    )
    defaults.update(overrides)
    event = models.Event(**defaults)
    db.add(event)
    db.flush()
    return event


def seed_floor(db: Session, application: models.Application, days_ago: int = 90) -> models.Event:
    """Anchor event establishing effective_bewerbung_floor() (sync_common.py) for
    tests exercising date-gated mail/calendar/call sync. An application with no
    dated events yet has no floor at all — "if there is absolutely no date
    available, do not sync timed events at all" (2026-07-16) — so any test whose
    application starts with zero events needs one of these before asserting a
    sync hit. Defaults to 90 days back, safely before same-day/near-term test
    dates; pass days_ago explicitly when a test uses an older fixed date."""
    return event_factory(db, application, datum=date.today() - timedelta(days=days_ago), source="icloud_mail")
