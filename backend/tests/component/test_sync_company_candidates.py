"""L1 Component — _collect_sync_candidates() in sync_company.py.

Regressionstest für einen Bug, der live an Produktivdaten gefunden wurde:
101 von 158 "done"-Firmen hatten kein Logo (meist kleine Personalberatungen,
für die Clearbit deterministisch nie ein Logo liefert) und wurden bei JEDEM
normalen Sync-Klick erneut als "unvollständig" erkannt und neu synct — obwohl
die UI sie bereits als "Synced" anzeigte. Ein fehlendes Logo ist ein
deterministisches Endergebnis, keine transiente Fehlerursache — nur eine
fehlende Beschreibung soll einen Retry auslösen.
"""
import pytest

from app.routers.sync_company import _collect_sync_candidates
from tests.factories import company_profile_factory

pytestmark = pytest.mark.component


class TestCollectSyncCandidates:
    def test_negativ_fehlendes_logo_allein_kein_retry(self, db_session):
        company_profile_factory(
            db_session, sync_status="done", description="Vorhanden", logo_data=None
        )

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert candidates == []

    def test_positiv_fehlende_beschreibung_loest_retry_aus(self, db_session):
        p = company_profile_factory(
            db_session, sync_status="done", description=None, logo_data="data:image/png;base64,xyz"
        )

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert [c.id for c in candidates] == [p.id]
        assert p.sync_status == "pending"  # als Nebenwirkung umgestellt, damit der Batch es abholt

    def test_corner_case_vollstaendiges_profil_kein_retry(self, db_session):
        company_profile_factory(
            db_session, sync_status="done", description="Da", logo_data="data:image/png;base64,xyz"
        )

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=None)

        assert candidates == []

    def test_positiv_pending_wird_immer_erfasst(self, db_session):
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
        target = company_profile_factory(db_session, sync_status="done", description=None)
        company_profile_factory(db_session, sync_status="done", description=None)  # außerhalb Scope

        candidates = _collect_sync_candidates(db_session, force=False, company_ids=[target.id])

        assert [c.id for c in candidates] == [target.id]
