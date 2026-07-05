L3 Integration-Tests (Fremdsysteme an der Netzwerkgrenze gemockt), siehe `docs/TEST_KONZEPT.md` Abschnitt 5.

**Umgesetzt:** KI-Provider (`conftest.py::fake_ai_provider` patcht `litellm.acompletion`, `test_ai_provider_flow.py`).

**Noch offen:** Gmail/Google Calendar (httpx/`google-api-python-client`), iCloud IMAP/CalDAV/CardDAV, LinkedIn (Playwright-Interception).

Laufen nur explizit über `pytest -m integration` bzw. bei Push auf `main` in CI — nicht Teil des PR-Gates (siehe `ci.yml`).
