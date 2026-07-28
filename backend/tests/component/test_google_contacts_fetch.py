"""L1 Component — fetch_all_google_contacts() in sync_google.py.

Mocks at the network boundary (googleapiclient.discovery.build), same
pattern as fake_google_calendar/fake_google_gmail in
tests/integration/conftest.py, but scoped to this one function rather than
a full sync flow — so it's a component test, not integration.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.ai.provider import encrypt_api_key
from app.routers.sync_google import fetch_all_google_contacts

pytestmark = pytest.mark.component


def _valid_cfg(db_session) -> models.GoogleSync:
    """Non-expired access token so _refresh_if_needed() doesn't attempt a
    real OAuth refresh call."""
    cfg = models.GoogleSync(
        client_id="test-client-id",
        client_secret_enc=encrypt_api_key("test-secret"),
        access_token_enc=encrypt_api_key("test-access-token"),
        refresh_token_enc=encrypt_api_key("test-refresh-token"),
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(cfg)
    db_session.commit()
    return cfg


class FakePeopleConnections:
    def __init__(self, pages: list[dict]) -> None:
        self._pages = list(pages)
        self._call_index = 0
        self.list_calls: list[dict] = []

    def list(self, **kwargs) -> "FakePeopleConnections":
        self.list_calls.append(kwargs)
        return self

    def execute(self) -> dict:
        page = self._pages[self._call_index]
        self._call_index += 1
        return page


class FakePeopleService:
    def __init__(self, pages: list[dict]) -> None:
        self._connections = FakePeopleConnections(pages)

    def people(self) -> "FakePeopleService":
        return self

    def connections(self) -> FakePeopleConnections:
        return self._connections


@pytest.fixture()
def fake_google_people(monkeypatch):
    """Returns a factory `set_pages(pages: list[dict]) -> FakePeopleService`.
    Each dict in `pages` is one raw People API connections().list() response
    (a "connections" list plus optional "nextPageToken")."""
    holder: dict[str, FakePeopleService] = {}

    def _fake_build(serviceName, version, credentials=None, cache_discovery=True):
        assert serviceName == "people", f"Only People API is mocked here, not {serviceName!r}"
        return holder["service"]

    def set_pages(pages: list[dict]) -> FakePeopleService:
        service = FakePeopleService(pages)
        holder["service"] = service
        return service

    monkeypatch.setattr("googleapiclient.discovery.build", _fake_build)
    return set_pages


def _person(display_name: str, family: str = "", given: str = "", email: str | None = None,
            phones: list[dict] | None = None, org_name: str | None = None, org_title: str | None = None,
            urls: list[str] | None = None) -> dict:
    person: dict = {"names": [{"displayName": display_name, "familyName": family, "givenName": given}]}
    if email:
        person["emailAddresses"] = [{"value": email}]
    if phones:
        person["phoneNumbers"] = phones
    if org_name or org_title:
        person["organizations"] = [{"name": org_name or "", "title": org_title or ""}]
    if urls:
        person["urls"] = [{"value": u} for u in urls]
    return person


class TestFetchAllGoogleContacts:
    async def test_positiv_liefert_normalisiertes_dict_gleich_parse_vcard(self, db_session, fake_google_people):
        cfg = _valid_cfg(db_session)
        fake_google_people([{
            "connections": [_person(
                "Jane Doe", family="Doe", given="Jane", email="jane@contoso.com",
                phones=[{"value": "+491234", "type": "mobile"}],
                org_name="Contoso AG", org_title="Recruiterin",
                urls=["https://linkedin.com/in/janedoe"],
            )],
        }])

        result = await fetch_all_google_contacts(cfg, db_session)

        assert result == [{
            "name": "Doe", "vorname": "Jane", "fn": "Jane Doe", "email": "jane@contoso.com",
            "phones": [{"number": "+491234", "type": "mobile"}],
            "firma": "Contoso AG", "rolle": "Recruiterin",
            "linkedin_url": "https://linkedin.com/in/janedoe",
        }]

    async def test_positiv_pagination_folgt_next_page_token(self, db_session, fake_google_people):
        cfg = _valid_cfg(db_session)
        service = fake_google_people([
            {"connections": [_person("Alice One", family="One", given="Alice")], "nextPageToken": "page2"},
            {"connections": [_person("Bob Two", family="Two", given="Bob")]},
        ])

        result = await fetch_all_google_contacts(cfg, db_session)

        assert [r["name"] for r in result] == ["One", "Two"]
        assert len(service._connections.list_calls) == 2
        assert service._connections.list_calls[1]["pageToken"] == "page2"

    async def test_negativ_person_ohne_namen_wird_uebersprungen(self, db_session, fake_google_people):
        cfg = _valid_cfg(db_session)
        fake_google_people([{"connections": [{"emailAddresses": [{"value": "noname@contoso.com"}]}]}])

        result = await fetch_all_google_contacts(cfg, db_session)

        assert result == []

    async def test_positiv_phone_type_mapping(self, db_session, fake_google_people):
        cfg = _valid_cfg(db_session)
        fake_google_people([{
            "connections": [_person(
                "Max Mustermann", family="Mustermann", given="Max",
                phones=[
                    {"value": "1", "type": "mobile"},
                    {"value": "2", "type": "home"},
                    {"value": "3", "type": "work"},
                    {"value": "4", "type": "main"},
                    {"value": "5", "type": "otherFax"},
                ],
            )],
        }])

        result = await fetch_all_google_contacts(cfg, db_session)

        types = {p["number"]: p["type"] for p in result[0]["phones"]}
        assert types == {"1": "mobile", "2": "home", "3": "work", "4": "main", "5": "other"}

    async def test_positiv_linkedin_url_wird_gefiltert(self, db_session, fake_google_people):
        cfg = _valid_cfg(db_session)
        fake_google_people([{
            "connections": [_person(
                "Jane Doe", family="Doe", given="Jane",
                urls=["https://contoso.com", "https://linkedin.com/in/janedoe"],
            )],
        }])

        result = await fetch_all_google_contacts(cfg, db_session)

        assert result[0]["linkedin_url"] == "https://linkedin.com/in/janedoe"

    async def test_negativ_leere_verbindungsliste_liefert_leere_liste(self, db_session, fake_google_people):
        cfg = _valid_cfg(db_session)
        fake_google_people([{"connections": []}])

        result = await fetch_all_google_contacts(cfg, db_session)

        assert result == []

    async def test_negativ_api_fehler_liefert_leere_liste(self, db_session, monkeypatch):
        cfg = _valid_cfg(db_session)

        def _raise_build(*args, **kwargs):
            raise RuntimeError("People API unreachable")

        monkeypatch.setattr("googleapiclient.discovery.build", _raise_build)

        result = await fetch_all_google_contacts(cfg, db_session)

        assert result == []
