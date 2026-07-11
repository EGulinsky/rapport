# rapport – Claude Code Context

Self-hosted application-tracking app (replacement for `Bewerbungen_Eugen_Gulinsky.xlsx`).
Runs locally in OrbStack (Docker Compose). Current status: see `CURRENT_VERSION` in `frontend/src/components/ChangelogModal.tsx`.

Full, continuously maintained technical documentation incl. Mermaid diagrams: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Starting the Project

```bash
# Start the app (OrbStack / Docker must be running)
cd /Users/eugengulinsky/code/rapport
docker compose up -d

# Rebuild after code changes
docker compose up -d --build

# Logs
docker compose logs -f backend
docker compose logs -f frontend
```

**URLs:**
- App: `http://192.168.117.10` (OrbStack static IP — no nginx cache issue)
- API/Swagger: `http://localhost:8000/docs`
- Alternative: `http://localhost:3000`

## Project Structure

Detailed, maintained overview (routers, components, data model): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#1-system-and-software-architecture). Short version:

```
rapport/
├── CLAUDE.md · README.md · docker-compose.yml (services: backend, frontend, seq)
│   docker-compose.test.yml    # Isolated test environment (own DB, ports 3001/8001)
├── .github/workflows/ci.yml   # Jobs: backend, frontend, e2e, docker, deploy, notify-failure
├── docs/
│   ├── ARCHITECTURE.md         # Technical architecture incl. Mermaid diagrams
│   └── TEST_KONZEPT.md         # Test concept (Phase 1–4 complete, Phase 5 E2E started)
├── backend/app/
│   ├── main.py · database.py · models.py · schemas.py
│   ├── audit.py · dedup.py · logger.py · linkedin_job_description.py
│   ├── ai/{provider,tasks}.py
│   └── routers/  applications · contacts · companies · merge · cleanup · test_e2e ·
│                 import_excel · export_excel · export_pdf · attachments ·
│                 settings · calendar · analytics · audit_log · backup ·
│                 sync_{common,google,icloud,targeted,files,linkedin,company} ·
│                 review · startup_check · auth
├── frontend/
│   ├── src/ (see below)
│   ├── e2e/                    # Playwright E2E tests (Phase 5)
│   │   ├── playwright.config.ts
│   │   ├── fixtures.ts         # authToken fixture (E2E_USER via /api/e2e/setup-user)
│   │   └── *.spec.ts           # user-journey tests
│   ├── Dockerfile.e2e          # mcr.microsoft.com/playwright as base
│   └── nginx.conf · nginx.test.conf
└── frontend/src/
    ├── App.tsx · types.ts · api/client.ts
    └── components/  ApplicationTable · KanbanBoard · ApplicationModal · …
```

## Database

SQLite at `/app/data/jobtracker.db` (Docker volume `jobtracker-data`).
Schema via SQLAlchemy `create_all()` on startup — no Alembic.

## Status Model

Two-tier: `main_status` + optional `sub_status`.

```
main_status: prospecting | applied | hr | fb | waiting | negotiating | signed | rejected
sub_status:  1_scheduled | 1_done | 2_scheduled | 2_done | 3_scheduled | 3_done | 4_scheduled | 4_done | 5_scheduled | 5_done
             (only relevant for hr and fb)
```

Pipeline (for `STATUS_ORDER` in sync):
```
prospecting → applied → hr → fb → waiting → negotiating → signed
                                                                └→ (all) → rejected
```

## Cryptography

All sensitive fields (passwords, OAuth tokens, API keys) are Fernet-encrypted.
Key: `backend/data/fernet.key` (in the Docker volume, never commit).
Functions: `encrypt_api_key()` / `decrypt_api_key()` in `app/ai/provider.py`.

## LinkedIn Scraper

Headless Playwright (Chromium) in the backend container.
Separate base image `Dockerfile.playwright-base` — only rebuilt on a Playwright version update.

**Categories** (order matters!):
```python
CATEGORIES = [
    ("SAVED", "Saved", "prospecting"),
    ("DRAFT", "Draft", "prospecting"),
    ("CLICKED_APPLY", "Applied (unconfirmed)", "prospecting"),
    ("APPLIED", "Applied", "applied"),
    ("INTERVIEWS", "Interviews", "hr"),
    ("ARCHIVED", "Archived", "rejected"),
]
```
LinkedIn's combined "In Progress" tab is just a client-side view of DRAFT + CLICKED_APPLY — `?stage=in-progress` always returns an empty page; the real slugs are `draft` and `clicked_apply`.

Every category gets its own `seen_ids = set()` — deliberately **not** shared, so ARCHIVED can overwrite the same job.

**2FA flow:** `_handle_2fa_checkpoint()` polls the URL:
- Option A: push notification on the phone → LinkedIn redirects away from `/checkpoint/` → auto-detected
- Option B: enter the code manually via `/api/sync/linkedin/submit-2fa`

## `naechster_schritt` (Next Step) Field

Computed field, **not** stored in the DB. `_compute_naechster_schritt()` in `applications.py` runs per GET request with three extra queries:
- `next_interviews`: min(datum) of future gespräch (interview) events
- `last_interviews`: max(datum) of past gespräch events
- `max_event_dates`: max(datum) across all events (≤ today, to exclude future appointments)

## `letztes_update` (Last Update)

The DB value is the manually set update date. In the `GET /api/applications/` endpoint it is overwritten in-memory by `max(events.datum WHERE datum <= today)` if larger — no `db.commit()` involved.

## Sync Sources and the Calendar Special Rule

Calendar sources (`gcal`, `icloud_cal`) create **no** status PendingMatches — only events.
Guard in `sync_common.py`: `if source not in ('gcal', 'icloud_cal'):`

## CI/CD

GitHub Actions self-hosted runner on the Mac.
Jobs: `backend` (ruff + pyright + `pytest -m "unit or component or api"`, 1122 tests) → `frontend` (tsc + vite build) → `e2e` (Playwright via docker-compose.test.yml, main push + workflow_dispatch) → `docker` (buildx, waits for e2e) → `deploy` (self-hosted). In addition, 184 L3 integration tests run on push to `main` (`pytest -m integration`).
Deploy: `git pull` → Docker Buildx builds new images on the runner → `docker compose up -d --build` → health poll → macOS notification. Details: [docs/TEST_KONZEPT.md](docs/TEST_KONZEPT.md) (test concept, all phases 1–6 complete).
A push to `main` always triggers test+deploy. Manually (e.g. on a feature branch) via `gh workflow run ci.yml --ref <branch>` to only test, or with `-f deploy=true` to also deploy (this always deploys the `main` head, regardless of the chosen `--ref`).

## Important Constants

- `CURRENT_VERSION` in `frontend/src/components/ChangelogModal.tsx` — bump on every content change
- OrbStack IPs: backend `192.168.117.10`, frontend `192.168.117.11`
- Fernet key file: `backend/data/fernet.key` (auto-generated on first startup)

## Rapport Agent (`agent/`)

Runs as a native macOS launchd program **outside** of Docker (menu-bar app, port 9996) — `docker compose up -d --build` does not touch it. Code changes in `agent/` need a real rebuild + reinstall:
```bash
cd agent && python3 -m venv .venv_build && .venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh <version>
```
Afterward, unload the old launchd job (`launchctl unload -w ~/Library/LaunchAgents/com.rapport.agent.plist`), copy the new app to `/Applications`, open it once (self-registers). Config/token lives in `~/Library/Application Support/RapportAgent/config.json` — preserved across app updates as long as the folder isn't deleted.

## E2E Tests (Playwright)

E2E tests run in the isolated test stack (`docker-compose.test.yml`):
```bash
# Start the test stack + run E2E tests
docker compose -p rapport-test -f docker-compose.test.yml up -d --build backend-test frontend-test
# Wait until the backend is ready, then:
docker compose -p rapport-test -f docker-compose.test.yml run --rm e2e-runner
# Clean up
docker compose -p rapport-test -f docker-compose.test.yml down -v
```

Test files live in `frontend/e2e/`. The base fixture (`fixtures.ts`) registers an E2E test user
via `POST /api/e2e/setup-user` (only active when `E2E_TESTING=true`). The auth token is
set in `localStorage`, after which the app loads as an authenticated user.

The JUnit report lands directly on the host at `e2e-report/test-results-e2e.xml` (bind-mounted
in `docker-compose.test.yml`'s `e2e-runner` service, `outputFile` set in `playwright.config.ts`) —
deliberately not read via `docker cp`, since `docker compose run` ignores the service's static
`container_name:` and mints a fresh random name every invocation. `e2e-report/` is gitignored.

## Excel File

Original: `/Users/eugengulinsky/Documents/Bewerbungen und Arbeitsverträge/Ich/Aktuell/Stellen/Bewerbungen_Eugen_Gulinsky.xlsx`
Sheet: `Tracking`, 17 columns — mapping in `models.py` under `EXCEL_IMPORT_MAP` / `EXCEL_EXPORT_MAP`.

## Work State (Session v3.55.12 – 2026-07-11)

Picks up right after the v3.55.0 session documented below (kept as historical reference).

### Completed in This Session

**Coverage: contacts.py + sync_company.py (v3.55.11):** `contacts.py` 80%→100% (`GET /` search/tenant-scoping/company-profile enrichment, `DELETE /bulk` gezielt + `all=true` — beide waren komplett ungetestet). `sync_company.py` 83%→99% (`_get_linkedin_context()` echter Playwright-Start + kaputtes Cookie-JSON, `resolve_company_candidate()`-Fehlerzweige, vollständiger `_run_sync_batch()`-Erfolgspfad über Wikidata inkl. Logo-Download — bisher liefen die Cancel-Tests nie bis zur SPARQL-Antwort durch).

**CI-Marker-Bug gefunden und gefixt (v3.55.11 + v3.55.12):** `tests/unit/test_linkedin_job_description.py` hatte seit Einführung keine `unit`/`component`/`api`/`integration`-Markierung (nur `pytest.mark.asyncio`) und lief dadurch nie unter dem CI-Marker-Filter (`-m "unit or component or api"`) — real 11% statt der zuvor angenommenen >90% (die alte Zahl kam aus einem isolierten Testlauf, der den Marker-Filter umgeht). Fix: `pytest.mark.unit` ergänzt. Zusätzlich ein zweites, unabhängiges Problem in derselben Datei gefunden: ein überflüssiges `pytest.mark.asyncio` auf Modulebene löste für drei synchrone Tests in `TestExtractionJs` bei jedem Lauf eine `PytestWarning` aus (`pytest.ini` setzt bereits `asyncio_mode = auto`). Systematisch geprüft: kein anderes Testfile hat eines der beiden Probleme.

**Testkonzept-Audit + Doku-Nachzug:** `docs/TEST_KONZEPT.md` und die CI/CD-Sektion in diesem Dokument enthielten veraltete Zahlen (602 statt 1306 Tests, 93 statt 184 Integrationstests, "Phase 1–4 complete, Phase 5 started" statt tatsächlich abgeschlossener Phasen 1–6). Beide korrigiert, inkl. einer neuen Coverage-Tabelle in Abschnitt 10 mit getrennten PR-Gate- vs. Integration-Zahlen (74% vs. 87% Gesamt-Coverage) — die alte Tabelle vermischte teils beide Messungen ohne das zu kennzeichnen.

**Nebenbefund zur Arbeitsweise:** Der `deploy`-Job aus `ci.yml` läuft auf demselben, nicht isolierten Arbeitsverzeichnis wie diese Session und führt nach grünem CI automatisch `git reset --hard origin/main` aus — ein währenddessen noch uncommitteter lokaler Edit wurde dadurch zweimal kommentarlos verworfen (über `git reflog` verifiziert). Lektion für künftige Sessions: nach jedem Push den CI-Status beobachten und vor Abschluss des laufenden `Deploy`-Jobs keine uncommitteten Änderungen offen liegen lassen (in Session-Memory dokumentiert).

### Open / Next Steps
- `sync_linkedin.py` bleibt bei 52% (PR-Gate wie kombiniert) — offener Rest ist der Playwright-Login/2FA/Scraping-Flow, der dedizierte Fixture-Infrastruktur über die bestehenden Mocks hinaus bräuchte
- `sync_targeted.py` PR-Gate-Coverage (28%) bleibt weit unter der kombinierten Zahl (77%) — rein strukturell durch die L3-lastige Testarchitektur der Datei, keine akute Lücke
- `respx`/`polyfactory` stehen weiterhin ungenutzt in `requirements-dev.txt` (Tests mocken `httpx` direkt per `unittest.mock.patch`, Factories sind bewusst einfache Funktionen) — Aufräumen oder tatsächlich einsetzen ist eine offene Entscheidung, keine akute Aufgabe

### Commits (this session, newest first)
```
5f4986c Fix: überflüssiges pytest.mark.asyncio in test_linkedin_job_description.py entfernt (v3.55.12)
93d45ae Tests: contacts.py + sync_company.py Testabdeckung angehoben, CI-Marker-Bug gefixt (v3.55.11)
```

---

## Work State (Session v3.55.0 – 2026-07-10) — historical

Current version: **v3.55.0** (build number from `frontend/src/version.ts`). Picks up right after the v3.51.0 session documented further below (kept as historical reference).

### Completed in This Session

**Documentation → English (v3.52.0):** all Markdown docs (`ARCHITECTURE.md`, `TEST_KONZEPT.md`, `Rapport_Konzept_Architektur.md`, `Rapport_Projektstand.md`, `CLAUDE.md`, `README.md`) plus all 34 closed GitHub issues (titles/bodies/comments) translated to English.

**Git history rewritten to English:** all 474 pre-existing commit messages translated and rewritten via `git-filter-repo --commit-callback` (content/tree hashes unchanged, verified — only commit metadata changed), then force-pushed to `main`. Safety net: backup tag `backup/pre-en-history-rewrite-2026-07-10` still points at the original (pre-rewrite) history. Local clones/forks made before this rewrite are diverged from `origin/main` and need a hard reset to `origin/main` to continue pushing.

**Account profile + CV upload (v3.53.0):** `User` model gained `vorname`, `nachname`, `linkedin_url`, `cv_filename`, `cv_content_type`, `cv_size_bytes`, `cv_storage_path` (migration `_migrate_user_profile()` in `database.py`). New endpoints in `routers/auth.py`: `PATCH /api/auth/profile`, `POST/GET/DELETE /api/auth/cv` (file stored at `{DB_DIR}/user_files/{user_id}/{filename}`, same pattern as `attachments.py`). Frontend: new "Profil"/"Lebenslauf" sections in `SettingsModal.tsx`'s `AccountPanel`. Groundwork for future AI use cases (e.g. auto-generated cover letters).

**Audit-Log — explicit type column + richer reasons (v3.54.0):** `AuditLog` gained an `entity_type` column (`application | contact | company | event`), derived automatically in `add_audit()` (`app/audit.py`) via the same contact > company > event > application precedence the frontend used to infer client-side — FK-based inference alone is unreliable (multiple FKs can be set at once, or none, as a company-merge bug demonstrated: it wrote no FK at all and was unfindable/untypeable, now fixed by setting `company_profile_id`). New filterable "Typ" column + badge in `AuditLogModal.tsx`. The `reason` field is now enriched with concrete context at sync/AI/matching call sites that already computed a "why" but discarded it — e.g. iCloud/targeted contact imports now say *why* a contact was pulled in ("in Bewerbungstext/E-Mail erwähnt"), AI-Bewertung includes the actual reasoning text, LinkedIn/company sync note the matched job-ID/URL/QID, PendingMatch approvals carry over confidence/extract. Manual (`source="user"`) changes are left without a synthesized reason, as before.

**CI: E2E test-report collection actually fixed (v3.54.1 → v3.54.2):** the "kein Testreport gefunden" step-summary warning had two stacked causes. v3.54.1 removed `--rm` from `docker compose run e2e-runner`, addressing a real but secondary issue (container removed before the follow-up `docker cp`) — this alone didn't fix it. The actual root cause: `docker compose run` **ignores** the service's static `container_name:` and mints a random `<project>-<service>-run-<hash>` name every time, so `docker cp rapport-e2e:...` was always targeting a container that never existed. v3.54.2 fixed it properly: Playwright now writes the JUnit report to a bind-mounted host directory (`e2e-report/` at repo root, mounted to `/app/e2e/e2e-report` in `docker-compose.test.yml`'s `e2e-runner` service; `playwright.config.ts`'s `outputFile` points there) — no `docker cp`, no container-name guessing. `--rm` was restored since it's no longer load-bearing. Verified locally end-to-end before pushing (13/13 E2E tests, report correctly written and parsed).

**Bulk-select/delete in the Bewerbung modal (v3.55.0):** Verlauf (timeline events), Anhänge (file-type events — same underlying model, different filter), and Kontakte (contacts linked to the application) can now be multi-selected (checkbox + "Alle auswählen" with indeterminate state) and deleted together. New backend endpoints `DELETE /api/applications/{id}/events/bulk` and `.../contacts/bulk` (both take `{ids: [...]}`, registered *before* their single-item `/{event_id}`/`{contact_id}` siblings in `applications.py` — otherwise Starlette's un-typed path matching would swallow `/bulk` as an `{event_id}` string and 422 instead of falling through). Events bulk-delete replicates the single-delete's `datum_bewerbung` recompute (once at the end, not per row); contacts bulk-delete replicates the single-delete's unlink-vs-hard-delete branching (a contact is only hard-deleted + audited once no other application references it).

**Test additions this session:** `backend/tests/unit/test_audit_entity_type.py` (entity_type inference), `test_audit_log_entities_api.py::TestEntityTypeApi` (API-level type/filter/merge-fix coverage), `test_auth_api.py::TestProfileAndCv` (10 tests), `test_applications_api.py::TestBulkDeleteEvents`/`TestBulkDeleteAppContacts` (9 tests). Backend suite: 682 tests total (579 unit/component/api + 93 integration), all green.

### Open / Next Steps
- LinkedIn message participant-matching context (point 4 from the audit-log investigation) still isn't surfaced in `reason` — lower priority, descriptive rather than a strong "why"
- The nested per-attachment pills inside `TimelineEvent.attachments` (real `Attachment` model rows, not the file-type-Event rows the Anhänge tab shows) still have no delete UI, individually or bulk
- `attachments.py`'s single `delete_attachment` still has no audit logging at all, unlike every other delete path in the codebase

### Commits (this session, newest first)
```
0c4c9cb Bewerbung: Verlauf, Anhänge und Kontakte mehrfach markieren und löschen (v3.55.0)
eff951a CI: E2E-Testreport wirklich reparieren via Bind-Mount statt docker cp (v3.54.2)
cec726b CI: E2E-Testreport-Sammlung reparieren (v3.54.1)
68d83d9 Audit-Log: eigene Typ-Spalte + konkreter Grund statt nur Quelle (v3.54.0)
5ccb784 Account profile: name, LinkedIn link, CV upload (v3.53.0)
7826de8 docs: translate all documentation to English (v3.52.0) — plus the 474-commit history rewrite force-pushed on top of the prior history
```

---

## Work State (Session v3.51.0 – 2026-07-10) — historical

### Completed in This Session

**Bugfix:**
- `_find_or_create_application()` in `sync_linkedin.py:1030` now calls `_ensure_company_profile(db, new_app)` so new LinkedIn applications immediately get a CompanyProfile (instead of `company_profile_id = NULL`).

**New backend endpoints** (`sync_linkedin.py`, end of file):
- `GET /api/sync/linkedin/companies/search?q=...` — LinkedIn company search (reusing `_get_linkedin_context` + `_linkedin_search_candidates` from `sync_company.py`)
- `POST /api/sync/linkedin/companies/import` — body `{candidates: [{name, url}]}`, deduplicates via `norm_firma()`, creates a `CompanyProfile`
- Both follow the pattern of `/people/search` and `/people/import`

**New frontend components:**
- `frontend/src/components/NewCompanyModal.tsx` — manual company creation (name → `api.companies.create()`), modeled on `NewContactModal`
- `frontend/src/components/CompanyImportModal.tsx` — LinkedIn search + multi-select + import (modeled on `ContactImportModal`, LinkedIn source only)

**App.tsx changes:**
- Added imports for both new modals
- State `showNewCompany`, `showCompanyImport` + `setShowCompanyImport`
- "New" dropdown: third branch for `mainView === 'companies'` with "Create manually" + "Import from LinkedIn"
- Modal rendering below the contact modals

**API client** (`frontend/src/api/client.ts`):
- `api.companies.searchLinkedIn(q: string)` → `GET /sync/linkedin/companies/search`
- `api.companies.importFromLinkedIn(candidates)` → `POST /sync/linkedin/companies/import`

**Types** (`frontend/src/types.ts`):
- Added `LinkedInCompanyCandidate { name, url, snippet? }`

**Tests (6 new files, +803 lines):**
- `backend/tests/api/test_analytics_tenant_scoping.py`
- `backend/tests/api/test_merge_edge_cases.py`
- `backend/tests/api/test_review_api.py`
- `backend/tests/component/test_cleanup_exec.py`
- `backend/tests/component/test_sync_common_purge_source.py`
- `backend/tests/unit/test_ai_response_schema.py`

**CI optimization:**
- Job timeout: backend 15min, frontend 10min, E2E 20min (`.github/workflows/ci.yml`)
- Background: a CI run hung for 24+ min; tests run locally in 62s / in CI in ~2min

**Coverage:** 39% overall (9673 lines, as of 2026-07-10)

### Open / Next Steps
- The new endpoints (`/companies/search`, `/companies/import`) don't have unit tests yet
- `NewCompanyModal` and `CompanyImportModal` don't have E2E tests yet
- Coverage gaps: `sync_google.py` 16%, `sync_icloud.py` 16%, `sync_linkedin.py` 39%

### Commits
```
8949e76 Tests: analytics tenant scoping, merge edge cases, review API, cleanup exec, purge source, AI response schema
3750b26 CI: job timeout 15min (backend) / 10min (frontend) / 20min (E2E)
4e6d2eb v3.51.0 LinkedIn company import + batch-sync company-profile fix
```

**Phase 4 gap closed:** `linkedin_job_description.py` went from 0% to >90% line coverage via 10 unit tests (mocked Playwright orchestration + JS-selector structure check).

**Nightly cron job:** `0 6 * * *` enabled in CI.

**L5 smoke job after deploy:** backend health, frontend load test, login + API call.

**E2E Journeys:**

| # | Journey | Status |
|---|---------|--------|
| 1 | Application lifecycle (create → status change → reject) | ✅ |
| 2 | Kanban drag & drop changes status incl. sub-status reset | ✅ |
| 3 | Import LinkedIn link → form pre-filled → save | ✅ |
| 4 | Cleanup button context-dependent (preview → run) | ✅ |
| 5 | Merge dialog (applications via table view) | ✅ |
| 6 | Targeted sync for one application (mocked sources) | ✅ |
| 7 | Manual candidate assignment (search → multiselect → import) | ✅ |
| 8 | AI assessment: "Reassess" → traffic light + reasoning | ✅ |
| 9 | Batch AI assessment with live progress (+ rate-limit simulation) | ✅ |
| 10 | Company sync with selection (only the chosen ones) | ✅ |
| 11 | Configure backup → manual run → restore | ✅ |
| 12 | Excel import (original format) → export → round-trip comparison | ✅ |

**Notes for implementation:**
- Put E2E tests in `frontend/e2e/`, follow the pattern in `application-lifecycle.spec.ts`
- Use `test.beforeEach` in the file or `test.describe.configure` for setup
- The `authToken` fixture automatically registers an E2E test user
- Selectors by text/content (no `data-testid` in the project)
- For mocked external sources: use Playwright `page.route()` interception
- Add a new test in the existing `.spec.ts` file or as a separate file
