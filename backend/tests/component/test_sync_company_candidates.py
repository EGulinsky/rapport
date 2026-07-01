"""L1 Component — _collect_sync_candidates() in sync_company.py.

Regressionstests für zwei live an Produktivdaten gefundene Bugs, beide
derselben Art: "done"-Firmen wurden bei JEDEM normalen Sync-Klick erneut
als "unvollständig" erkannt und neu synct, obwohl die UI sie bereits als
"Synced" anzeigte.

1. (v3.17.3) 101 von 158 "done"-Firmen hatten kein Logo — Clearbit-Lookup
   ist deterministisch, ein einmal fehlendes Logo bleibt fehlend.
2. (v3.17.6) Nachdem (1) über "fehlende Beschreibung → Retry" behoben wurde,
   trat derselbe Fehler dort erneut auf: 8 kleine/obskure Firmen (kein
   Web-Auftreten, z.B. eine türkische Firma ohne Online-Präsenz) wurden
   bereits erfolglos durchsucht (last_synced_at gesetzt, sync_source=
   "duckduckgo"), aber weil description weiterhin None war, wurden sie bei
   jedem weiteren Sync-Klick erneut als "unvollständig" behandelt — eine
   identische Suche liefert aber garantiert wieder nichts.

Endergebnis: "done" heißt jetzt wirklich fertig, unabhängig davon, ob
Logo/Beschreibung gefunden wurden. Nur "Re-Sync" (force=True) versucht es
für bereits abgeschlossene Profile nochmal — das ist eine bewusste
User-Aktion, kein automatischer Hintergrund-Retry.
"""
import pytest

from app.routers.sync_company import _collect_sync_candidates
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


class TestCollectSyncCandidates:
    def test_negativ_fehlendes_logo_kein_retry(self, db_session):
        company_profile_factory(
            db_session, sync_status="done", description="Vorhanden", logo_data=None
        )

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert candidates == []

    def test_negativ_fehlende_beschreibung_kein_retry(self, db_session):
        # Regressionsfall v3.17.6: "done" + description=None (bereits erfolglos
        # versucht) darf NICHT automatisch erneut aufgegriffen werden.
        p = company_profile_factory(
            db_session, sync_status="done", description=None, logo_data="data:image/png;base64,xyz"
        )

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert candidates == []
        assert p.sync_status == "done"  # bleibt unverändert, kein stiller Statuswechsel

    def test_negativ_beides_fehlt_trotzdem_kein_retry(self, db_session):
        company_profile_factory(
            db_session, sync_status="done", description=None, logo_data=None
        )

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert candidates == []

    def test_positiv_pending_wird_immer_erfasst(self, db_session):
        # Echte Neuanlage (noch nie versucht) — das einzige, was ein
        # normaler "Sync"-Klick abholt.
        p = company_profile_factory(db_session, sync_status="pending")

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert [c.id for c in candidates] == [p.id]

    def test_positiv_force_erfasst_auch_vollstaendige_profile(self, db_session):
        p = company_profile_factory(
            db_session, sync_status="done", description="Da", logo_data="data:image/png;base64,xyz"
        )

        candidates = _collect_sync_candidates(db_session, force=True, company_ids=None)

        assert [c.id for c in candidates] == [p.id]

    def test_corner_case_company_ids_scoped(self, db_session):
        target = company_profile_factory(db_session, sync_status="pending")
        company_profile_factory(db_session, sync_status="pending")  # außerhalb Scope

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=[target.id])

        assert [c.id for c in candidates] == [target.id]
