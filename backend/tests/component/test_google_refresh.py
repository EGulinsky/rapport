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
from app.routers.sync_google import _build_credentials, _refresh_if_needed

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
    def test_positiv_erfolgreicher_refresh_speichert_neuen_token(self, db_session, monkeypatch):
        cfg = _expired_cfg(db_session)

        def _fake_refresh(self, request):
            self.token = "refreshed-access-token"
            self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

        monkeypatch.setattr(Credentials, "refresh", _fake_refresh)

        result = _refresh_if_needed(cfg, db_session)

        assert result.token == "refreshed-access-token"
        assert cfg.access_token_enc is not None
        assert cfg.token_expiry is not None

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

    def test_negativ_invalid_scope_loescht_tokens_und_wirft_hilfreiche_meldung(self, db_session, monkeypatch):
        # Live beobachtet: eine vor Einführung des contacts.readonly-Scopes
        # verbundene Google-Verbindung schlug bei JEDEM Sync (nicht nur
        # Contacts) mit "invalid_scope: Bad Request" fehl, weil der Refresh
        # dieses neue Scope anforderte, obwohl der gespeicherte Refresh-Token
        # nie dafür autorisiert wurde. Gleiche Behandlung wie invalid_grant.
        cfg = _expired_cfg(db_session)

        def _raise_invalid_scope(self, request):
            raise Exception("invalid_scope: Bad Request")

        monkeypatch.setattr(Credentials, "refresh", _raise_invalid_scope)

        with pytest.raises(RuntimeError, match="neu verbinden"):
            _refresh_if_needed(cfg, db_session)

        assert cfg.access_token_enc is None
        assert cfg.refresh_token_enc is None
        assert cfg.token_expiry is None


class TestBuildCredentials:
    def test_positiv_keine_scopes_gesetzt_um_refresh_grant_nicht_einzuschraenken(self, db_session):
        # google-auth sendet ein "scope"-Feld im Refresh-Request nur, wenn
        # Credentials.scopes gesetzt ist — und Google lehnt den Refresh mit
        # invalid_scope ab, falls dort ein Scope steht, den der gespeicherte
        # Refresh-Token nie erhalten hat (z.B. bei Verbindungen von vor der
        # Einführung von contacts.readonly). Kein `scopes=` an Credentials()
        # übergeben lässt das Refresh-Scope unverändert (RFC 6749 §6).
        cfg = _expired_cfg(db_session)

        creds = _build_credentials(cfg)

        assert not creds.scopes
