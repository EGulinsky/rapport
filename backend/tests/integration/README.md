L3 integration tests (external systems mocked at the network boundary), see `docs/TEST_KONZEPT.md` section 5.

**Implemented:**
- AI provider (`conftest.py::fake_ai_provider` patches `litellm.acompletion`, `test_ai_provider_flow.py`)
- Google Calendar (`conftest.py::fake_google_calendar` patches `googleapiclient.discovery.build`, `test_google_calendar_sync.py`)
- Gmail (`conftest.py::fake_gmail` + `gmail_message()` helper, `test_gmail_sync.py`) — covers the two-phase batch fetch (`new_batch_http_request`, metadata first then full text), not just plain `.execute()` calls
- LinkedIn status logic (`_process_linkedin_job()`, `test_process_linkedin_job.py` — pure DB logic, no Playwright mock needed)
- iCloud Mail (IMAP), Calendar, Reminders, Contacts, Notes, and Calls (`test_icloud_*_sync.py`) — each both as a global sync and via targeted single-application sync (`test_sync_targeted_icloud_*.py`)
- `sync_targeted.py`'s full `_do_sync()` flow, domain/text-match filtering, and the five live-candidate searches (`test_sync_targeted_do_sync.py`, `test_sync_targeted_domains.py`, `test_sync_targeted_live_candidates.py`)

**Careful when extending:** sync functions (`_do_gcal`, `_do_gmail`, …) open their own `SessionLocal()` internally. Test setup done via the `db_session` fixture must be **committed** before the call (`db_session.commit()`, not just `flush()`) — otherwise SQLite blocks until the `busy_timeout` (60s), and the test just runs very slowly instead of failing immediately. This has already happened live **twice** (Calendar and Gmail tests) — check explicitly for this whenever adding a new test case, not just the first time.

**Still open:** LinkedIn (Playwright interception) — per section 8 this actually belongs in the nightly tier; the current `linkedin_job_description.py` unit tests (Playwright mocked directly, not via `page.route()` interception) cover the job-description scraping path but not the login/2FA/search-result-scraping flow in `sync_linkedin.py` / `sync_company.py`.

Only runs explicitly via `pytest -m integration` or on push to `main` in CI — not part of the PR gate (see `ci.yml`).
