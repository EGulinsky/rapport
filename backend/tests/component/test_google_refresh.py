"""L1 Component — _refresh_if_needed() in sync_google.py.

Deckt den Token-Refresh-Fehlerpfad ab, der weder von den Calendar- noch den
Gmail-Integrationstests erreicht wird (beide nutzen die google_sync-Fixture
mit gültigem, nicht abgelaufenem Token). Mockt gezielt Credentials.refresh()
selbst — keine echten Netzwerkaufrufe an Googles OAuth-Endpoint.
"""
from datetime import datetime, timedelta, timezone

import pytest
from google.oauth2.credentials import Credentials

from app import models
from app.ai.provider import encrypt_api_key
from app.routers.sync_google import _refresh_if_needed

pytestmark = pytest.mark.component


def _expired_cfg(db_session) -> models.GoogleSync:
    cfg = models.GoogleSync(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        access_token_enc=None,  # fehlender Token erzwingt den Refresh-Pfad unabhängig von token_expiry
        refresh_token_enc=encrypt_api_key("test-refresh-token"),
        token_expiry=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


class TestRefreshIfNeeded:
    def test_negativ_invalid_grant_loescht_tokens_und_wirft_hilfreiche_meldung(self, db_session, monkeypatch):
        cfg = _expired_cfg(db_session)

        def _raise_invalid_grant(self, request):
            raise Exception("invalid_grant: Token has been expired or revoked.")

        monkeypatch.setattr(Credentials, "refresh", _raise_invalid_grant)

        with pytest.raises(RuntimeError, match="neu verbinden"):
            _refresh_if_needed(cfg, db_session)

        assert cfg.access_token_enc is None
        assert cfg.refresh_token_enc is None
        assert cfg.token_expiry is None

    def test_negativ_widerrufener_token_loescht_ebenfalls(self, db_session, monkeypatch):
        cfg = _expired_cfg(db_session)

        def _raise_revoked(self, request):
            raise Exception("Token has been revoked by the user.")

        monkeypatch.setattr(Credentials, "refresh", _raise_revoked)

        with pytest.raises(RuntimeError, match="neu verbinden"):
            _refresh_if_needed(cfg, db_session)

        assert cfg.refresh_token_enc is None

    def test_negativ_anderer_refresh_fehler_wird_unveraendert_durchgereicht(self, db_session, monkeypatch):
        # Ein transienter Netzwerkfehler o.ä. soll NICHT die Tokens löschen —
        # nur eindeutig irreversible Fälle (invalid_grant/revoked) tun das.
        cfg = _expired_cfg(db_session)

        def _raise_timeout(self, request):
            raise Exception("connection timed out")

        monkeypatch.setattr(Credentials, "refresh", _raise_timeout)

        with pytest.raises(Exception, match="connection timed out"):
            _refresh_if_needed(cfg, db_session)

        assert cfg.refresh_token_enc is not None  # unangetastet
