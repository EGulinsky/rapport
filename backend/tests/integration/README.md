L3 Integration-Tests (Fremdsysteme an der Netzwerkgrenze gemockt), siehe `docs/TEST_KONZEPT.md` Abschnitt 5.

**Umgesetzt:**
- KI-Provider (`conftest.py::fake_ai_provider` patcht `litellm.acompletion`, `test_ai_provider_flow.py`)
- Google Calendar (`conftest.py::fake_google_calendar` patcht `googleapiclient.discovery.build`, `test_google_calendar_sync.py`)

**Achtung beim Erweitern:** Sync-Funktionen (`_do_gcal`, `_do_gmail`, …) öffnen intern eine eigene `SessionLocal()`. Test-Setup über die `db_session`-Fixture muss vor dem Aufruf **committet** sein (`db_session.commit()`, nicht nur `flush()`) — sonst blockiert SQLite bis zum `busy_timeout` (60s), der Test läuft dann nur sehr langsam statt sofort zu failen. Live in dieser Session gefunden (siehe `conftest.py`-Docstring).

**Noch offen:** Gmail (Batch-Requests, komplexer als Calendar), iCloud IMAP/CalDAV/CardDAV, LinkedIn (Playwright-Interception).

Laufen nur explizit über `pytest -m integration` bzw. bei Push auf `main` in CI — nicht Teil des PR-Gates (siehe `ci.yml`).
