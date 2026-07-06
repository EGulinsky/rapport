"""L1 Component — MergeAlias-Fallback in _find_or_create_application() (sync_linkedin.py).

Nach einem manuellen Zusammenführen (merge.py) verliert die "Verlierer"-Bewerbung
ihre Identität, aber ihre alten Kennungen (LinkedIn-Job-ID bzw. Firma+Rolle)
werden in merge_aliases festgehalten — damit ein späterer LinkedIn-Sync, der
noch die alte Kennung liefert, trotzdem die kanonische (überlebende) Bewerbung
findet, statt fälschlich ein Duplikat neu anzulegen.
"""
import pytest

from app import models
from app.routers.sync_linkedin import _find_or_create_application
from tests.factories import application_factory

pytestmark = pytest.mark.component


def _job(**overrides) -> dict:
    base = dict(
        id="", title="Backend Engineer", company="Contoso AG", ort=None,
        applied_date=None, default_status="applied", status_hint=None, hinweis="",
        stellenanzeige_url=None,
    )
    base.update(overrides)
    return base


class TestMergeAliasFallback:
    def test_positiv_alias_ueber_li_job_id_findet_kanonische_bewerbung(self, db_session):
        # Kanonische Bewerbung trägt bereits eine andere Firma/Rolle-Schreibweise
        # (nach dem Merge aktualisiert) — der direkte firma+rolle-Match (Schritt 2)
        # würde daher NICHT greifen; nur der Alias führt zum richtigen Treffer.
        canonical = application_factory(db_session, firma="Contoso Deutschland GmbH", rolle="Senior Backend Engineer")
        db_session.add(models.MergeAlias(
            entity_type="application", canonical_id=canonical.id, alias_li_job_id="4433221100",
        ))
        db_session.commit()

        app, created, pending, match_grund = _find_or_create_application(
            db_session, _job(id="4433221100", company="Ganz andere Schreibweise AG", title="Andere Rolle"),
        )

        assert created is False
        assert app.id == canonical.id
        assert "alias→" in match_grund

    def test_positiv_alias_ueber_firma_und_rolle_findet_kanonische_bewerbung(self, db_session):
        canonical = application_factory(db_session, firma="Contoso Deutschland GmbH", rolle="Senior Backend Engineer")
        db_session.add(models.MergeAlias(
            entity_type="application", canonical_id=canonical.id,
            alias_firma="Contoso AG", alias_rolle="Backend Engineer",
        ))
        db_session.commit()

        app, created, pending, match_grund = _find_or_create_application(
            db_session, _job(company="Contoso AG", title="Backend Engineer"),
        )

        assert created is False
        assert app.id == canonical.id
        assert "alias→" in match_grund

    def test_positiv_li_job_id_backfill_auf_kanonischer_bewerbung(self, db_session):
        # Die kanonische Bewerbung hat selbst noch keine linkedin_job_id — der
        # Alias-Treffer soll sie nachtragen, damit künftige Syncs den schnelleren
        # direkten Job-ID-Pfad (Schritt 1) nutzen können.
        canonical = application_factory(db_session, firma="Contoso Deutschland GmbH", rolle="Senior Backend Engineer", linkedin_job_id=None)
        db_session.add(models.MergeAlias(
            entity_type="application", canonical_id=canonical.id, alias_li_job_id="4433221100",
        ))
        db_session.commit()

        app, *_ = _find_or_create_application(
            db_session, _job(id="4433221100", company="Ganz andere Schreibweise AG", title="Andere Rolle"),
        )

        assert app.linkedin_job_id == "4433221100"

    def test_negativ_alias_auf_geloeschte_bewerbung_faellt_auf_neuanlage_zurueck(self, db_session):
        # canonical_id zeigt ins Leere (Bewerbung wurde inzwischen gelöscht) —
        # darf nicht crashen, sondern muss sauber auf "neu anlegen" zurückfallen.
        db_session.add(models.MergeAlias(
            entity_type="application", canonical_id=999999, alias_li_job_id="9999999999",
        ))
        db_session.commit()

        app, created, pending, match_grund = _find_or_create_application(
            db_session, _job(id="9999999999", company="Contoso AG", title="Backend Engineer"),
        )

        assert created is True
        assert "neu→" in match_grund

    def test_negativ_alias_eines_anderen_entity_type_wird_ignoriert(self, db_session):
        # Ein Kontakt-Alias mit zufällig übereinstimmendem li_job_id-Wert darf
        # nicht fälschlich als Bewerbungs-Alias interpretiert werden.
        db_session.add(models.MergeAlias(
            entity_type="contact", canonical_id=1, alias_li_job_id="4433221100",
        ))
        db_session.commit()

        app, created, pending, match_grund = _find_or_create_application(
            db_session, _job(id="4433221100", company="Contoso AG", title="Backend Engineer"),
        )

        assert created is True
