import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { BUILD_NUMBER } from '../version'

interface Release {
  version: string
  date: string
  changes: string[]
}

const CHANGELOG: Release[] = [
  {
    version: '4.1.3',
    date: '2026-07-16',
    changes: [
      'Fixed a production outage caused by v4.1.2 itself: the PDF-parsing library used for CV text extraction can occasionally spin at ~100% CPU for minutes on certain real-world PDFs without ever finishing, and since that ran during app startup (backfilling existing CV uploads), it blocked the entire app from starting. CV extraction now runs with a hard 20-second timeout — a file that\'s too slow to parse is skipped (no CV text for that assessment) rather than blocking anything.',
    ],
  },
  {
    version: '4.1.2',
    date: '2026-07-16',
    changes: [
      'Fixed the AI assessment (v4.1.0) taking a very long time to run. It was re-parsing your CV file (PDF/DOCX text extraction) synchronously on every single assessment, and doing so inside the request handler blocked the whole app for everyone while it ran — the same class of bug just fixed for iCloud sync (v4.1.1), reintroduced by that CV/LinkedIn feature itself. CV text is now extracted once when you upload the file and reused from then on; existing uploads are backfilled automatically on next startup.',
    ],
  },
  {
    version: '4.1.1',
    date: '2026-07-14',
    changes: [
      'Fixed a bug where a slow response from Apple\'s iCloud servers during the automatic Mail/Calendar/Reminders sync could freeze the entire app for everyone, not just that sync — a real ~20-minute outage caused by this. The iCloud sync now runs those network calls off the main thread instead of blocking it.',
    ],
  },
  {
    version: '4.1.0',
    date: '2026-07-14',
    changes: [
      'AI assessment now considers your CV and LinkedIn profile, not just the application timeline. If you\'ve uploaded a CV (Settings → Account), its text is automatically included; a new "Sync profile" button next to your LinkedIn URL lets you cache your profile text (reusing your existing LinkedIn session) for the assessment to weigh candidate/role fit alongside the usual timeline signals. Both are optional — assessments look exactly as before if you haven\'t set either up.',
    ],
  },
  {
    version: '4.0.0',
    date: '2026-07-14',
    changes: [
      'Major version: rapport is now cross-platform. The native Rapport Agent (local file access, notes, calls) runs on macOS, Windows, and Linux, each hardware-verified end to end — not just unit-tested with mocks. Windows and Linux packaging ships as a self-contained installer with the same self-registration-at-login behavior macOS has had all along.',
    ],
  },
  {
    version: '3.79.1',
    date: '2026-07-14',
    changes: [
      'Fixed a deploy-time data-loss risk introduced by the portability work: docker-compose.yml had dropped the explicit volume names (to auto-create the database volume on a fresh install), but on an existing deployment that made Docker Compose create a brand-new, empty volume instead of reusing the real one — silently swapping in an empty database with no accounts. Restored the explicit volume name so it both reuses an existing deployment\'s data and still auto-creates cleanly on a first install.',
    ],
  },
  {
    version: '3.79.0',
    date: '2026-07-13',
    changes: [
      'Agent portability: real hardware verification of the Windows and Linux packaged builds (previously only unit-tested with mocks), which surfaced and fixed three genuine bugs invisible to CI. Windows service self-registration used Task Scheduler, but `schtasks /create` returns Access Denied under a normal (non-elevated) user token even for a task that only runs at that user\'s own logon — replaced with the HKCU `Run` registry key, the same no-elevation approach already used on macOS (launchd) and Linux (systemd --user).',
      'The packaged Windows agent\'s server silently failed to start: a windowed (no-console) build has no usable standard output/error streams, which crashed the logging setup invisibly. Fixed by redirecting to a log file whenever a real console isn\'t available.',
      'The packaged Linux agent crashed outright on any machine without a graphical display (a server, an SSH session) instead of degrading to headless mode as intended, because the display library raises a different error than the one the fallback was watching for. Now caught, so it degrades gracefully like it always should have.',
    ],
  },
  {
    version: '3.78.0',
    date: '2026-07-13',
    changes: [
      'Fixed three remaining i18n gaps in backend-generated content: the sync progress dialog (both per-application and full-account sync) was entirely German regardless of account language — every step message across Gmail, Google Calendar, iCloud Mail/Notes/Calendar/Reminders/Contacts/Calls, local-file sync, and LinkedIn (including the login/2FA flow) is now generated in the account\'s UI language via a shared translation table, mirroring the pattern already used for backend error keys.',
      'AI assessment (traffic-light reasoning and next-step suggestion) now writes its reasoning in the account\'s selected language instead of always German — the prompt sent to the AI provider now carries an explicit language instruction derived from account settings.',
      'The audit log\'s "reason" column had ~50 call sites across sync, merge, review, and company-matching code that always wrote German text regardless of account language; all now resolve to the account\'s language the same way error messages already did.',
    ],
  },
  {
    version: '3.77.0',
    date: '2026-07-12',
    changes: [
      'i18n: translated the entire changelog history to English — all 311 entries, going all the way back to v0.1.0. Reverses an earlier decision this same day to leave historical entries in German; going forward, every changelog entry (new and old) stays in English, matching the existing "commits always in English" rule. Also translated the "current" badge in this modal\'s own header, which had been hardcoded German (`aktuell`) since it was never covered by any of the i18n phases.',
    ],
  },
  {
    version: '3.76.0',
    date: '2026-07-12',
    changes: [
      'i18n: full codebase re-scan for leftover German strings, beyond the per-component sweeps of the last few releases. Found and fixed two more real gaps: SyncButton.tsx (the app-shell sync dropdown, progress overlay, 2FA prompt, and sync-summary modal — 519 lines, entirely hardcoded German) via a new `sync` i18n namespace, and ReviewModal\'s event-type filter dropdown, which rendered raw internal keys ("gespräch", "notiz", "angebot", "absage") as visible option text instead of translating them.',
      'i18n: `<html lang>` was hardcoded to "de" in index.html and never updated at runtime, so it stayed wrong for any English-language session (affects screen readers, browser spell-check, and translate prompts). Now kept in sync with the active UI language on load and on every language switch.',
    ],
  },
  {
    version: '3.75.0',
    date: '2026-07-12',
    changes: [
      'i18n gap fixes: ApplicationTable\'s empty state, column headers (Company/Role, Source, Status, Applied, Update, Assessment), the "· Rejected" suffix, and the AI-confidence labels (High/Low/Medium) were all hardcoded German despite the component already using translations elsewhere — added a new `table` section to the applications namespace and wired it in.',
      'i18n bugfix: the Analytics view\'s funnel chart, status donut, "rejections by phase" chart, and "applications over time" chart all displayed status/month names baked into the backend response in German only (analytics.py computes a display label server-side, independent of the account\'s language) — the frontend now recomputes each label from the stable status/month key that was already being sent alongside it, so these charts actually follow the UI language. Added a regression test asserting the raw backend label never reaches the screen.',
    ],
  },
  {
    version: '3.74.0',
    date: '2026-07-12',
    changes: [
      'i18n gap fix: AuditLogModal.tsx had been completely missed by the original 13-phase i18n sweep — title, buttons, filters, table headers, and the action/type/source label maps were all hardcoded German. Translated via a new auditLog namespace, with a component test proving the language switch (matching the pattern already used for StatusBadge and StatsBar). The free-text "reason" column stays untranslated, same as other dynamic backend-generated content.',
    ],
  },
  {
    version: '3.73.0',
    date: '2026-07-12',
    changes: [
      'i18n bugfix: even with v3.72.0\'s fix, a language push still had no visible effect — the agent\'s menu bar is built once by rumps at process startup, so writing the new language to disk alone never changed what was on screen. The agent now restarts itself automatically whenever a push actually changes the language (launchd immediately relaunches it with the new language already active), instead of requiring a manual quit-and-reopen.',
    ],
  },
  {
    version: '3.72.0',
    date: '2026-07-12',
    changes: [
      'i18n bugfix: the v3.71.0 fix itself was silently broken — the backend pushed the agent\'s language via HTTP POST, but the agent\'s `/config` endpoint only accepts PATCH, so every push (both from Settings → Agent and Settings → Account) failed with a 405 that was swallowed by design (an unreachable agent must not block a profile save). Added a dedicated `agent_patch()` helper and switched both call sites to it — language changes now actually reach the agent.',
    ],
  },
  {
    version: '3.71.0',
    date: '2026-07-12',
    changes: [
      'i18n bugfix: changing your language in Settings → Account now actually reaches an already-paired agent. Previously only re-saving the Agent token in Settings → Agent pushed `ui_language` to the agent\'s `/config` endpoint — a plain language switch in Account settings updated the database but never notified the agent, so its menu bar silently kept showing the old language until the token was re-saved for an unrelated reason.',
    ],
  },
  {
    version: '3.70.0',
    date: '2026-07-12',
    changes: [
      'i18n follow-up: translated backend error keys (from Phase 10) are now actually shown to users. ApplicationModal, CompanyModal, ContactModal, MergeDialog, CleanupModal, NewCompanyModal, NewContactModal, and the company-contact-linking flow all displayed the raw caught-error message instead of translating it via the `errorKey`/`errors` namespace — fixed by routing every catch block for applications/contacts/companies/attachments/merge endpoints through the existing errorMessage() helper (already used on the 6 auth pages).',
      'CI now runs a curated English-language E2E subset (application lifecycle, company sync, backup/restore) on every push to main, alongside the existing full German-language run — closing a gap left open in Phase 12\'s test-selector refactor.',
    ],
  },
  {
    version: '3.69.0',
    date: '2026-07-12',
    changes: [
      'i18n (Phase 13/13, wrap-up): final completeness sweep across the entire component tree — found and fixed two previously overlooked spots: the "change status" tooltip in the application table (new common.json key changeStatus) and PdfExportButton.tsx, a completely untranslated legacy component no longer used anywhere since the move to ImportExportMenu.tsx — removed rather than translated. New StatsBar test adds a second component-level language-switch proof alongside the existing StatusBadge test (different namespace: app instead of status). With this, all 13 planned i18n phases are complete — the web app, backend error messages, native Mac agent, and E2E tests now support German/English throughout, switchable per account.',
    ],
  },
  {
    version: '3.68.0',
    date: '2026-07-12',
    changes: [
      'i18n (Phase 12/13, E2E selectors): all 12 Playwright specs converted from German-text selectors to stable data-testid attributes — covers App.tsx, ApplicationModal.tsx, CleanupModal.tsx, MergeDialog.tsx, CompaniesView.tsx, StatusBadge.tsx, and the backup panel. Discovered and translated a component that had been completely missed until now: ImportExportMenu.tsx (Excel/PDF export, Excel import). New authToken fixture option `uiLanguage` (still defaulting to "de") lays the groundwork for future test runs in other languages. The actual CI setup for an additional English test run (see plan) is still open.',
    ],
  },
  {
    version: '3.67.0',
    date: '2026-07-12',
    changes: [
      'i18n (Phase 11/13, Rapport Agent): the native Mac agent (menu bar) now also supports German/English — new agent/strings.py with all menu/dialog text, a new AgentConfig.ui_language field, and a new PATCH /config endpoint that the backend calls automatically with the account language whenever the agent token is saved/verified. Since rumps only builds the menu once at startup, a language change only takes effect after the agent is restarted. Important: this phase requires a manual rebuild + reinstall of the agent on the Mac in addition to the code (see agent/README.md) — green CI alone doesn\'t mean it\'s "done".',
    ],
  },
  {
    version: '3.66.0',
    date: '2026-07-12',
    changes: [
      'i18n (Phase 10/13, backend error keys): "not found" errors in applications.py, contacts.py, companies.py, attachments.py, and merge.py now return stable error_key values instead of just German text — 38 call sites converted, fixing two existing inconsistencies along the way (companies.py used English text in two places, merge.py had a grammar error for contacts). Backend-only change, no visible effect yet — the affected frontend dialogs so far only partially translate error messages via the error_key mechanism.',
    ],
  },
  {
    version: '3.65.0',
    date: '2026-07-12',
    changes: [
      'i18n (Phase 9/13, Settings dialog): all 12 Settings tabs (Account, Sync, AI/API, Google, iCloud, Calls, Documents, LinkedIn, Backup, Logos, Maps, Agent) are now fully translated — tab names, forms, sync status, AI provider badges, LinkedIn action log, and all hint texts. New settings.json namespace (de+en, ~150 keys).',
    ],
  },
  {
    version: '3.64.0',
    date: '2026-07-12',
    changes: [
      'i18n (Phase 8/13, application detail dialog): the entire application detail dialog (2400+ lines) is now translated — header with company picker, sync menu, lifecycle bar, all four tabs (overview, timeline, attachments, contacts) including all forms, the manual-assign dialog, and the document browser. New applications.json namespace (de+en, ~150 keys).',
    ],
  },
  {
    version: '3.63.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 7/13, calendar + analytics + small dialogs): the calendar view (month/week view, view switcher, detail popup), the entire analytics page (KPI tiles, funnel, bottleneck analysis, stage conversion, headhunter-vs-direct, all chart titles/legends/tooltips), StatsBar, the startup warning banner messages, the duplicate-cleanup dialog, and the manual-review dialog are now fully translated. New namespaces calendar.json/analytics.json/cleanup.json/review.json (de+en); app.json extended with stats/startupWarning.',
    ],
  },
  {
    version: '3.62.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 6b/13, company detail + merge): the company detail dialog (profile/applications/contacts tabs, edit form, logo upload, contact assignment), the companies overview table (sync menu, link contacts, assign parent company), and all three merge dialogs (applications/contacts/companies) are now fully translated. New merge.json namespace; companies.json extended with companyType/syncSource labels and the company detail view.',
    ],
  },
  {
    version: '3.61.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 6a/13, contacts + company dialogs): the entire contacts view is now translated — table, company assignment, merge/delete actions, "new contact" dialog, iCloud/LinkedIn import dialog, and the contact detail dialog including the edit form. Also the small company dialogs "new company" and LinkedIn company import. New contacts.json/companies.json namespaces de+en (company detail/list follow in Phase 6b).',
    ],
  },
  {
    version: '3.60.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 5/13, date formats): every date/time formatting call site previously hardcoded to "de-DE", plus one sort collation (localeCompare), is now language-aware — 23 call sites across 9 files (company detail, contacts, contact detail, audit log, Kanban, calendar, application table, application detail, settings). New formatDate()/formatDateTime()/collate() helpers in i18n/formatDate.ts wrap this uniformly for both components and standalone helper functions, now backed by their own tests.',
    ],
  },
  {
    version: '3.59.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 4/13): the entire app shell in App.tsx is now translated — navigation, search bar, status filter, "AI assess"/"Clean up"/"New" buttons including the dropdown menu, LinkedIn import dialog, and the new-application form. Switching language (at registration or in Settings → Account) now immediately affects the entire visible app chrome — only the individual views (Contacts, Companies, Calendar, Analytics, Settings itself) remain German for now, following in the next phases.',
    ],
  },
  {
    version: '3.58.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 3/13): Settings → Account now has a language selector (German/English) that takes effect app-wide immediately. The status labels (Prospecting, Applied, Interview HR/HH, …) moved from a static German list in types.ts into the new language catalogs and are now translated at all 9 places that display them (table, Kanban, calendar, suggested changes, merge dialog, application detail).',
    ],
  },
  {
    version: '3.57.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 2/13, login/registration): the registration dialog now has a language selector (German/English, defaulting to English) — all 6 auth pages (login, registration, forgot/reset password, verify email) are fully translated and switch live. Backend: auth error messages (wrong password, code invalid/expired, email not verified, CV validation, …) now return a stable error_key instead of just German text — the frontend translates it, with the previous German text as a fallback for anything not yet keyed. Verification/reset emails are now sent server-side in the account\'s chosen language.',
    ],
  },
  {
    version: '3.56.0',
    date: '2026-07-11',
    changes: [
      'i18n (Phase 1/13, foundations): accounts now have a UI language (ui_language, defaulting to "de" for existing accounts, "en" for new registrations) — DB migration, register/profile endpoints, /api/e2e/setup-user. Frontend: react-i18next scaffolding (i18n/index.ts, useLocale/formatDate/collate helpers, first common.json namespace de+en) plus a test ensuring every language catalog has the same keys. No visible change yet — the actual language selection (registration + settings) follows in the next phase.',
    ],
  },
  {
    version: '3.55.14',
    date: '2026-07-11',
    changes: [
      'Docs: CLAUDE.md now documents the second working checkout /Users/eugengulinsky/code/rapport-dev — Claude Code sessions work there so the automatic deploy job (git reset --hard in /rapport) never again discards uncommitted edits (has happened twice, see session history).',
    ],
  },
  {
    version: '3.55.13',
    date: '2026-07-11',
    changes: [
      'Docs: docs/TEST_KONZEPT.md and the CI/CD section in CLAUDE.md had stale numbers (602 instead of 1306 tests, 93 instead of 184 integration tests, "Phase 5 started" instead of Phases 1–6 actually being complete) — both updated, including a new coverage table with separate PR-gate vs. integration figures (74% vs. 87%).',
      'Docs: agent/README.md and backend/tests/integration/README.md had stayed entirely in German (missed during the v3.52.0 doc translation, or created afterward) — translated to English, the latter also updated in content (iCloud Mail/Calendar/Reminders/Contacts/Notes/Calls have long been implemented, no longer "still open").',
    ],
  },
  {
    version: '3.55.12',
    date: '2026-07-11',
    changes: [
      'Fix: test_linkedin_job_description.py also had a superfluous module-level pytest.mark.asyncio, which triggered a PytestWarning on every run for the three synchronous tests in TestExtractionJs (pytest.ini already sets asyncio_mode=auto, the explicit marker was never needed).',
    ],
  },
  {
    version: '3.55.11',
    date: '2026-07-11',
    changes: [
      'Fix: test_linkedin_job_description.py had never run in CI since it was introduced — it was missing the pytest.mark.unit marker that the marker filter (`-m "unit or component or api"`) needs to run it. As a result, linkedin_job_description.py sat at 11% in real CI runs instead of the assumed 82%.',
      'Tests: contacts.py from 80% to 100% test coverage — GET /api/contacts/ (search, tenant scoping, company enrichment from linked CompanyProfiles) and DELETE /api/contacts/bulk (targeted and all=true) were completely untested.',
      'Tests: sync_company.py from 83% to 99% test coverage — _get_linkedin_context() (real Playwright start, broken cookie JSON), resolve_company_candidate() error branches (SPARQL errors, logo fallbacks), and the full successful _run_sync_batch() path via Wikidata including logo download, which previously only ran in the cancel tests before the SPARQL response arrived.',
    ],
  },
  {
    version: '3.55.10',
    date: '2026-07-10',
    changes: [
      'Tests: sync_linkedin.py from 43% to 52% test coverage — config/status/run/2FA endpoints plus people/company search-import fully tested. The remaining part (login flow, 2FA checkpoint, scraping) needs dedicated Playwright fixture infrastructure (see open item).',
    ],
  },
  {
    version: '3.55.9',
    date: '2026-07-10',
    changes: [
      'Tests: main.py from 33% to 86% test coverage — _run_source() concurrency guard, _auto_link_contacts(), /health + /api/sync/schedule/status, and the complete background sync loop (source selection per settings, due backups, error resilience).',
    ],
  },
  {
    version: '3.55.8',
    date: '2026-07-10',
    changes: [
      'Tests: sync_targeted.py from 58% to 77% test coverage — new tests for the complete _do_sync() flow (AI assessment, per-source error collection) and the five live candidate searches (Gmail/GCal/iCloud Mail/Calendar/Notes).',
    ],
  },
  {
    version: '3.55.7',
    date: '2026-07-10',
    changes: [
      'Tests: applications.py, companies.py, settings.py, sync_files.py, export_pdf.py, import/export_excel.py, attachments.py, auth/email.py, and sync_company.py each raised to 83–100% test coverage.',
      'Fix: export_pdf.py — a Content-Disposition header with an umlaut in the filename wasn\'t RFC-6266-compliant and broke under strict HTTP clients; now RFC-5987 encoded.',
      'Fix: export_excel.py — show_rejected=false triggered a 500 (filtering on a plain Python property instead of a database column).',
    ],
  },
  {
    version: '3.55.6',
    date: '2026-07-10',
    changes: [
      'Tests: sync_icloud.py from 51% to 83% test coverage — new tests for status/credentials/reset endpoints, mail/calendar/reminders error branches, the active notes and call-log sync, and CardDAV contact enrichment.',
    ],
  },
  {
    version: '3.55.4',
    date: '2026-07-10',
    changes: [
      'Tests: ai/tasks.py from 64% to 100% test coverage — 34 new tests cover all seven AI functions (classify_for_app, batch fallback/rate-limit branches, test_connection, assess_rejected_application, extract_application_from_text).',
    ],
  },
  {
    version: '3.55.3',
    date: '2026-07-10',
    changes: [
      'Tests: database.py (inline SQLite migrations) from 12% to 96% test coverage — 83 new tests cover all 26 migration functions (column/table creation, backfills, idempotency).',
    ],
  },
  {
    version: '3.55.2',
    date: '2026-07-10',
    changes: [
      'Tests: increased test coverage — calendar.py, audit_log.py, sync_common.py, and backup.py each to ≥86% (previously 73–79%), 37 new tests.',
    ],
  },
  {
    version: '3.55.1',
    date: '2026-07-10',
    changes: [
      'Docs: CLAUDE.md updated with the current session state (doc translation, git history rewrite, account profile/CV, audit-log type/reason, CI E2E report fix, multi-select delete).',
    ],
  },
  {
    version: '3.55.0',
    date: '2026-07-10',
    changes: [
      'New: within an application, timeline entries, attachments, and contacts can now be multi-selected and deleted together (checkboxes + "select all" per tab).',
    ],
  },
  {
    version: '3.54.2',
    date: '2026-07-10',
    changes: [
      'Fix (follow-up to v3.54.1): the actual reason for the missing E2E test report wasn\'t just the removed --rm, but that "docker compose run" ignores the configured container_name and assigns a random one instead — so the docker cp step never found the right container. The JUnit report is now written straight to the host via a bind mount, without guessing a container name at all.',
    ],
  },
  {
    version: '3.54.1',
    date: '2026-07-10',
    changes: [
      'Fix: the CI "collect test results" step never found an E2E test report, because --rm removed the Playwright container immediately after the test run, before the following docker cp step could read it ("no test report found"). Only affected the report summary, not the actual CI result (Playwright still reported failures correctly).',
    ],
  },
  {
    version: '3.54.0',
    date: '2026-07-10',
    changes: [
      'New: the audit log now shows its own type column (application/contact/company/event) with a filter, instead of only being able to infer the type indirectly via the reference column.',
      'Improved: for automatic changes (sync, AI, PendingMatch approval), the reason column now shows the concrete trigger instead of just the source — e.g. "mentioned in application text/email" or the AI reasoning instead of just "AI assessment".',
      'Fix: company-merge entries in the audit log previously had no company reference, making them neither findable nor typeable.',
    ],
  },
  {
    version: '3.53.0',
    date: '2026-07-10',
    changes: [
      'New: account profile extended with first name, last name, and LinkedIn link, plus CV upload (PDF/DOC/DOCX) — groundwork for later AI use cases like auto-generated cover letters.',
    ],
  },
  {
    version: '3.52.0',
    date: '2026-07-10',
    changes: [
      'Docs: translated all Markdown documents (ARCHITECTURE.md, TEST_KONZEPT.md, Rapport_Konzept_Architektur.md, Rapport_Projektstand.md, CLAUDE.md, README.md) to English.',
    ],
  },
  {
    version: '3.51.2',
    date: '2026-07-10',
    changes: [
      'Performance: the LinkedIn sync for a single application no longer searches the entire archive (up to 99 pages) — that was the slowest part, even though a freshly targeted-synced application is practically never found there. Only already-rejected applications still get searched in the archive as well.',
    ],
  },
  {
    version: '3.51.1',
    date: '2026-07-10',
    changes: [
      'Fix: merging (applications/contacts/companies) now cleanly rejects with an understandable error message when the winner was accidentally also selected as a loser, instead of failing with a confusing "not found" message.',
      'CI: fixed a lint error (unused import) and 4 failing merge regression tests from the last commit.',
    ],
  },
  {
    version: '3.51.0',
    date: '2026-07-10',
    changes: [
      'Fix: batch sync now creates a CompanyProfile for new LinkedIn applications.',
      'New: create companies manually via the "New" button in the companies tab.',
      'New: import companies from LinkedIn (search + multi-select).',
      'New: GET/POST /api/sync/linkedin/companies/search + /import endpoints.',
    ],
  },
  {
    version: '3.50.4',
    date: '2026-07-09',
    changes: [
      'Fix: L5 frontend smoke test: while loop over localhost:3000.',
      'Optimization: Docker build now runs in parallel with E2E (removed an unnecessary dependency).',
    ],
  },
  {
    version: '3.50.0',
    date: '2026-07-09',
    changes: [
      'L5 smoke test after deploy: backend health, frontend load test, login + API call.',
      'Test concept Phases 1–6 fully complete.',
    ],
  },
  {
    version: '3.49.0',
    date: '2026-07-09',
    changes: [
      'Closed the Phase 4 gap: linkedin_job_description.py from 0% to >90% coverage via 10 unit tests.',
      'Nightly cron job (0 6 * * *) enabled in CI for integration + E2E.',
      'Volume mount for backend tests in docker-compose.test.yml — no more rebuild needed for test changes.',
    ],
  },
  {
    version: '3.48.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 12: Excel import, export, and round-trip via the import/export menu button.',
      'Test concept Phase 5 complete — all 12 E2E user journeys implemented.',
    ],
  },
  {
    version: '3.47.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 11: configure backup, manual backup run, show backup list, restore with confirmation dialog.',
    ],
  },
  {
    version: '3.46.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 10: company sync with selection of multiple companies and scoped sync (no auto-continue).',
    ],
  },
  {
    version: '3.45.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 9: batch AI assessment with an SSE mock (page.route with delay) and rate-limit simulation.',
    ],
  },
  {
    version: '3.44.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 8: AI assessment (reassess → traffic light + reasoning) with a mocked /ai-assess endpoint.',
    ],
  },
  {
    version: '3.43.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 7: manual candidate assignment via page.evaluate for checkbox selection in the dialog overlay.',
    ],
  },
  {
    version: '3.42.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 6: targeted sync with mocked backend endpoints (page.route) and a title-based sync-button selector.',
    ],
  },
  {
    version: '3.41.0',
    date: '2026-07-09',
    changes: [
      'E2E Journey 5: merge dialog (merging two applications with different fields via the table view). Fix: CI docker build check now runs before deploy.',
    ],
  },
  {
    version: '3.40.0',
    date: '2026-07-08',
    changes: [
      'E2E Journey 4: cleanup (detect + delete duplicates). Fix: CleanupModal called onDone() synchronously right after setPhase("done") → React 18 batching closed the modal before the "cleanup complete" message rendered. onDone() is now async via setTimeout(200).',
    ],
  },
  {
    version: '3.39.0',
    date: '2026-07-08',
    changes: [
      'E2E Journeys 1-3: application lifecycle, Kanban status change, and LinkedIn import now run stably under Docker/E2E. Fix: backend POST /api/companies returned a ResponseValidationError (app_count was missing). Journeys 1+2 use API setup instead of the UI form (more robust). Selectors switched to exact/last (strict-mode conflicts with column headers). All three tests green.',
    ],
  },
  {
    version: '3.38.0',
    date: '2026-07-08',
    changes: [
      'E2E Journey 3: import a LinkedIn link → form pre-filled → save. Mocks the backend endpoint /api/applications/extract-from-linkedin-url via page.route(), checks that company, role, source, and comment are pre-filled in NewApplicationModal, and saves the application.',
    ],
  },
  {
    version: '3.37.0',
    date: '2026-07-08',
    changes: [
      'E2E Journey 2: Kanban drag & drop — drag a card by mouse (page.mouse) from "Applied" to "Interview HR/HH" (status change), set a sub-status, then drag the card to "Offer negotiation" (sub-status reset verified via the backend). Custom dragTo function for @dnd-kit compatibility (PointerSensor + 8px activation constraint).',
    ],
  },
  {
    version: '3.36.0',
    date: '2026-07-08',
    changes: [
      'Test concept Phase 5 (E2E): built Playwright infrastructure with a Docker-based E2E runner, test-user setup via /api/e2e/setup-user, first E2E test for the application lifecycle (create, status change, rejection). New CI job "E2E (Playwright)" runs on push to main — starts an isolated test stack (docker-compose.test.yml), runs the Playwright suite, and tears everything down. linkedin_job_description.py still at 0% (Phase 4 gap, earmarked for Phase 6).',
    ],
  },
  {
    version: '3.35.1',
    date: '2026-07-08',
    changes: [
      'PDF export: "appointments from the last 4 weeks" now only considers real calendar entries (interviews or Google/iCloud calendar), no more calls — same definition as the calendar tab.',
    ],
  },
  {
    version: '3.35.0',
    date: '2026-07-08',
    changes: [
      'The audit log now also records all creations, changes, and deletions of contacts, companies, and calendar entries — previously applications only. Covers manual actions (merging contacts/companies, manually assigning/moving an appointment, resetting sync) as well as automatic sync operations (new contacts from emails/iCloud, company enrichment via LinkedIn/Wikidata, synced appointments) equally. The audit log dialog now shows the respective reference (contact/company/appointment, with the associated application where relevant) directly in the overview.',
    ],
  },
  {
    version: '3.34.5',
    date: '2026-07-08',
    changes: [
      'Audit log: closed several gaps where changes to applications weren\'t being logged — including some fields in the edit dialog (location, headhunter flag, interview notes), company assignment, sub-status changes, AI assessment, automatic date backfill, silent LinkedIn-sync corrections, non-status fields when merging applications, and duplicates auto-deleted during cleanup. New source "Automatic" for entries that don\'t originate from a manual action.',
    ],
  },
  {
    version: '3.34.4',
    date: '2026-07-07',
    changes: [
      'New: "resend code" on the verify-email page. Previously there was no way to get a new confirmation code if the original one had expired or sending had failed — re-registering with the same address failed with "already registered".',
    ],
  },
  {
    version: '3.34.3',
    date: '2026-07-07',
    changes: [
      'User accounts Phase 3/5 + 4/5: real tenant separation is now active. Every endpoint requires login and returns only the logged-in account\'s own data (applications, contacts, companies, appointments, all sync settings). New login/registration UI including email verification and forgot-password flow, plus a new "Account" tab in Settings for changing password and logging out.',
    ],
  },
  {
    version: '3.34.2',
    date: '2026-07-07',
    changes: [
      'Security: replaced password-like test fixture strings in test_auth_api.py with values clearly recognizable as test data, to avoid recurring GitGuardian false positives on hardcoded test passwords. No functional change.',
    ],
  },
  {
    version: '3.34.1',
    date: '2026-07-07',
    changes: [
      'User accounts Phase 2/5: tenant separation in the database. All 20 previously global tables (applications, contacts, company profiles, appointments, all sync settings) now have an account association. The existing (accountless) data is automatically assigned to the first confirmed account as soon as someone registers and verifies for the first time. Not yet active: endpoints don\'t yet filter by account (comes in Phase 3) — until then, access remains open as before.',
    ],
  },
  {
    version: '3.34.0',
    date: '2026-07-07',
    changes: [
      'New feature (Phase 1/5, backend foundation): user accounts with email+password. Registration with a 6-digit confirmation code by email, login, password reset by code, change password — /api/auth/register, /verify-email, /login, /forgot-password, /reset-password, /me, /change-password. Not yet active: existing applications/contacts/settings aren\'t yet tied to accounts (comes in Phase 2/3), the frontend login UI follows in Phase 4.',
    ],
  },
  {
    version: '3.33.15',
    date: '2026-07-06',
    changes: [
      'Test concept: 49 new tests for LinkedIn import focused on job postings, company name, and application date — date parsing ("3d/2w/3mo ago", absolute formats), text extraction of multiple job entries (company, dedup, status hints), LinkedIn job-ID matching, and carrying over company name/application date when creating new applications. sync_linkedin.py from 37% to 42% coverage.',
    ],
  },
  {
    version: '3.33.14',
    date: '2026-07-06',
    changes: [
      'CI: added a manual workflow_dispatch trigger for ci.yml — allows choosing "test only" (default) or "test + deploy" (via the deploy input), similar to classic make test/make deploy targets. Push to main behaves unchanged (always test+deploy).',
    ],
  },
  {
    version: '3.33.13',
    date: '2026-07-06',
    changes: [
      'Doc polish: brought stale test numbers in CLAUDE.md/README.md (still "271 tests"/"Phase 1–3") up to date (357 PR-gate tests, Phase 1–4). Pure doc correction, no code changed.',
    ],
  },
  {
    version: '3.33.12',
    date: '2026-07-06',
    changes: [
      'Test concept Phase 4 (iCloud mocking) complete: 7 new tests for the notes sync. Found along the way that the active notes sync has long run through the local Rapport agent instead of a direct Apple ID login — only the old, unused login path remained untested. sync_icloud.py to 50%, overall coverage to 54%. This completes Phase 4 of the test concept except for LinkedIn Playwright fixture replay.',
    ],
  },
  {
    version: '3.33.11',
    date: '2026-07-06',
    changes: [
      'Test concept Phase 4 (iCloud mocking) continued: 14 new tests for iCloud contacts (CardDAV) — both globally and in the targeted per-application sync, including regression tests for two mass-import bugs that had occurred live before (contacts from orphaned company profiles with no real application link, or with no matching email domain). sync_icloud.py to 45%, sync_targeted.py to 57%, overall coverage to 53%.',
    ],
  },
  {
    version: '3.33.10',
    date: '2026-07-06',
    changes: [
      'Fix: calendar appointments and reminders synced via iCloud were saved with a broken title (raw text like "<SUMMARY{}Interview at Contoso>" instead of "Interview at Contoso") — affected every calendar/reminder entry synced via iCloud. Found and fixed while building the corresponding tests.',
      'Test concept Phase 4 (iCloud mocking) started: 31 new tests for iCloud Mail (IMAP), Calendar, and Reminders (CalDAV) — both globally and in the targeted per-application sync. sync_icloud.py from 23% to 43%, sync_targeted.py from 38% to 53%, overall coverage to 52%.',
    ],
  },
  {
    version: '3.33.9',
    date: '2026-07-06',
    changes: [
      'Test concept: raised test coverage of the targeted per-application sync (sync_targeted.py, the second-largest backend file) from 5% to 38% — 72 new tests for search-term/domain logic, the API endpoints (reset, candidate list, manual assignment), domain-based filtering of Gmail/Calendar, and the agent-based sources (iCloud notes, calls).',
      'Fix: calendar appointments created via targeted sync (Google + iCloud) didn\'t set the external ID, so they couldn\'t be reliably found again in the candidate list/manual assignment — found while writing the corresponding tests. Overall coverage rose to 47% as a result.',
    ],
  },
  {
    version: '3.33.8',
    date: '2026-07-06',
    changes: [
      'Test concept Phase 4: ran a targeted gap analysis of existing error-case coverage and closed 5 blind spots with 18 new tests — missing AI configuration/disabled provider, invalid API key, unsupported JSON mode, and unknown model during AI assessment; "not connected to Google" for calendar and Gmail sync; expired/revoked Google token on refresh; and the LinkedIn merge-alias fallback after manually merging applications. Overall coverage rose to 42% as a result, `ai/provider.py` to 96%.',
    ],
  },
  {
    version: '3.33.7',
    date: '2026-07-06',
    changes: [
      'Test concept Phase 4 continued: 7 new L3 integration tests for the Gmail sync — first covers the two-phase batch fetch (message metadata first, then full text for relevant matches), including pagination across multiple pages and a partial batch error without a full abort. Google sync area (Gmail + Calendar) thus from 12% to 62% test coverage.',
    ],
  },
  {
    version: '3.33.6',
    date: '2026-07-06',
    changes: [
      'Fix: every new application created via LinkedIn sync generated a pointless review entry ("New (LI archive): applied → X"), even when X was exactly the status the application was already created with — affected every status except rejections. Found while writing the corresponding tests: 8 such no-op entries were already sitting in the real review queue. Now a review entry is only created for actual archive/rejection cases.',
      'Test concept Phase 4 continued: extracted the LinkedIn sync\'s status-transition and duplicate-avoidance logic (previously only reachable via a real sync run) into a standalone, testable function and backed it with 9 tests — including regression protection for the old issues #9/#14 (repeated status suggestions).',
    ],
  },
  {
    version: '3.33.5',
    date: '2026-07-05',
    changes: [
      'Test concept Phase 4 continued: 5 new L3 integration tests for the Google Calendar sync (contact match, change detection, deleting orphaned appointments, Calendar API errors) via a fake for googleapiclient. Found and documented a test trap along the way: sync functions internally open their own DB session — uncommitted test fixtures otherwise block until the SQLite busy_timeout (60s) instead of failing immediately.',
    ],
  },
  {
    version: '3.33.4',
    date: '2026-07-05',
    changes: [
      'Added measured test coverage to the test concept (343 tests total, 36% backend line coverage) — with a breakdown of which areas already hit the 80% goal (dedup/status/crypto) and where the biggest gaps are (sync routers: targeted 5%, google 12%, icloud 23%, linkedin 30%). Pure doc addition, no code changed.',
    ],
  },
  {
    version: '3.33.3',
    date: '2026-07-05',
    changes: [
      'Test concept Phase 4 started: first L3 integration tests for the AI provider flow (assess_application, match_and_classify, batch classification including a fallback regression for the wrong response size) — mocking at the network boundary (litellm.acompletion), not the business logic itself. Run on every push to main in addition to the existing PR gate.',
    ],
  },
  {
    version: '3.33.2',
    date: '2026-07-05',
    changes: [
      'Brought docs up to date (the architecture doc still described the old DuckDuckGo/Wikipedia company sync and the old LinkedIn category list instead of Wikidata and Draft/Clicked-apply; added missing routers/tables) and replaced real company names/personal data from earlier bug regression tests and changelog entries with generic placeholders — preparation for making the repo public.',
    ],
  },
  {
    version: '3.33.1',
    date: '2026-07-05',
    changes: [
      'Completed the rename throughout: Docker containers, the repo folder (now `~/code/rapport`), the GitHub repo (github.com/EGulinsky/rapport), and the local Mac background service ("Rapport Agent", formerly "JobTracker Agent") are now consistently named rapport. App URLs moved accordingly (e.g. backend.rapport.orb.local instead of backend.jobtracker.orb.local). Applications, contacts, and settings remained unchanged.',
    ],
  },
  {
    version: '3.33.0',
    date: '2026-07-05',
    changes: [
      'The app is now called "rapport" (instead of "JobTracker") and got its own logo — visible in the browser tab title, favicon, and README. Reason: the previous name was purely descriptive and stood in the way of making the repo public with clear recognizability.',
    ],
  },
  {
    version: '3.32.4',
    date: '2026-07-04',
    changes: [
      'Fix: jobs in LinkedIn\'s "In Progress" status were completely skipped during sync. Cause: on LinkedIn, "In Progress" is just a combined view of two real subcategories ("Draft" and "Clicked apply") that need their own, working URLs — the URL used until now always returned an empty page. Both subcategories are now correctly recognized and picked up as "Prospecting" as expected (not "Applied"), since LinkedIn itself asks whether the application was even completed for "Clicked apply".',
    ],
  },
  {
    version: '3.32.3',
    date: '2026-07-03',
    changes: [
      'Fix: saving a contact (e.g. when manually splitting into first/last name) failed with a 500 error as soon as "last contact" contained a date — the field was mistyped in the edit endpoint (text instead of date) and the database rejected the raw text. Affected every contact edit with a date set, not just the name split.',
    ],
  },
  {
    version: '3.32.2',
    date: '2026-07-03',
    changes: [
      'Fix: the previous change (separate first/last name columns) showed the full name in the last-name column for almost all existing contacts, because the iCloud import never read the vCard\'s structured first/last name field, only the (inconsistently formatted) display name. It now uses the real address-book field — reliable regardless of whether the display name reads "First Last" or "Last First". 169 of 198 existing contacts were automatically corrected from the real address-book data, the rest deliberately left unchanged instead of guessed (e.g. for company entries).',
    ],
  },
  {
    version: '3.32.1',
    date: '2026-07-03',
    changes: [
      'Contacts overview: first name and last name are now separate, sortable columns instead of a combined name. Editing them separately was already possible in the detail modal — now also visible directly in the overview.',
    ],
  },
  {
    version: '3.32.0',
    date: '2026-07-03',
    changes: [
      'After every completed sync (main sync, company sync, application sync, LinkedIn sync from Settings), "manual review" now opens automatically as soon as there\'s something to decide — previously you had to click the bell yourself, even if something had been open for a while.',
      'Company disambiguation in the review dialog: with multiple LinkedIn matches, a one-line summary with industry and location now appears next to name and link (e.g. "IT Services and IT Consulting · San Francisco, California") — helps distinguish e.g. "GitLab" from "GitLab Foundation" or "Peach Tech (Acquired by GitLab)".',
    ],
  },
  {
    version: '3.31.3',
    date: '2026-07-03',
    changes: [
      'LinkedIn contact import: company detection from the headline now also recognizes "Role @ Company" (not just "at"/"bei"). Deliberately NOT added: splitting on "|", since many headlines use that for skill lists instead of "Role | Company" — that would have produced wrong companies. For profiles with a custom headline that mentions no company at all (e.g. just "Head of Customer Program Management"), the company stays empty instead of being guessed — LinkedIn\'s access restriction for not-directly-connected profiles ("visible with Premium only") prevents a reliable look at the full profile page as a fallback. The import dialog now points out this limitation.',
    ],
  },
  {
    version: '3.31.2',
    date: '2026-07-03',
    changes: [
      'Fix: iCloud contact search returned 0 results when every matching vCard was already an imported contact (searching "qorix" found 3 real matches but wrongly showed an empty result). Already-existing contacts are now still shown, just marked as "already added" instead of hidden.',
      'Fix: LinkedIn people search often showed results without company/headline — caused by people only mentioned as "X, Y, and 20 other mutual connections" inside someone else\'s card; they were wrongly counted as their own search results and used up the result quota, making it look like only the first results page came back. Real search results are now recognized by connection degree ("• 1st/2nd/3rd"), plain mentions are discarded.',
    ],
  },
  {
    version: '3.31.1',
    date: '2026-07-03',
    changes: [
      'Contact import from iCloud/LinkedIn now uses the existing global "New" button instead of separate buttons in the contacts overview — the "New" menu shows the right options depending on context (in the contacts view: create manually / from iCloud / from LinkedIn instead of the application options). "Import from LinkedIn" now correctly means people import instead of job-posting import in the contacts view.',
    ],
  },
  {
    version: '3.31.0',
    date: '2026-07-03',
    changes: [
      'Contacts overview: besides manual creation, now also targeted import from the full iCloud address book ("From iCloud") and from LinkedIn people search ("From LinkedIn") — with search, multi-select, and "import N". Unlike the automatic sync, there\'s no relevance check here: the user deliberately searches for a specific person and decides for themselves. The new LinkedIn people search uses the existing session (no extra login) and automatically splits headlines like "Senior Engineer at Contoso" into role/company. Verified live, finding and fixing a bug in the connection-degree text along the way ("• 3rd+", which sometimes stuck directly to the name).',
    ],
  },
  {
    version: '3.30.0',
    date: '2026-07-03',
    changes: [
      'Applications could previously only manually create two entry types directly (note, application) — mail, call, offer, rejection, status/interview, and file attachments only existed if they came from a sync source or the AI review queue. New: "Other" (freely choose any remaining entry type) and "Attachment" (file upload directly to an application — the backend endpoint for it already existed but wasn\'t wired up anywhere in the frontend) in the timeline. The type of an existing entry can now also be changed to any type (except attachments), not just the original four.',
    ],
  },
  {
    version: '3.29.1',
    date: '2026-07-03',
    changes: [
      'Fix: in "manual review" (the review modal), clicking "accept"/"reject" (individually or as a batch) gave no visible feedback while the request was running (e.g. for company-sync selections with a LinkedIn scrape/Wikidata fallback in the background) — felt like it had hung. Buttons now show a spinner and "Processing…" while the action is running.',
    ],
  },
  {
    version: '3.29.0',
    date: '2026-07-03',
    changes: [
      'Reversed the company-sync order: the LinkedIn company page is now primary, Wikidata is only a fallback when there are 0 LinkedIn matches. With multiple plausible LinkedIn matches for a company, it\'s no longer auto-guessed — it lands as an open entry in the existing "manual review" queue (the settings bell), where you pick the right candidate or click "none of these" (which then triggers the Wikidata fallback for just that one company). Verified live on "GitLab", finding and fixing a real bug along the way: LinkedIn\'s search-result link wraps the entire result card (name, industry, location, description), so the detected company name initially contained the whole card text instead of just the name.',
    ],
  },
  {
    version: '3.28.1',
    date: '2026-07-03',
    changes: [
      'Fix: a cancelled company sync (cancel while running) wrongly marked companies for which a Wikidata entry had already been found, but whose detail data hadn\'t been fetched yet, as "done, no record" instead of re-queuing them for the next run — under the "done never auto-retries" rule, they would otherwise have stayed permanently stuck with empty data. Noticed live during the first production sync run after the Wikidata switch (over 150 affected companies), now backed by a regression test.',
    ],
  },
  {
    version: '3.28.0',
    date: '2026-07-03',
    changes: [
      'Fundamentally reworked company sync: Wikidata (search + structured company data) is now the primary source instead of DuckDuckGo/Wikipedia — fixes a data-quality bug where 127 of 183 companies identically showed "software development" as their industry (an overly generic search term had confused the legal form with the industry). New: LinkedIn company-page fallback for companies without a Wikidata entry (uses the existing LinkedIn session, no extra login). New: automatic rough startup/SME/enterprise classification from employee count + founding year, once fresh data is available. Verified live against production data (several real company profiles, including ones with a subsidiary structure), finding and fixing two real bugs along the way: an abort bug that would have wrongly marked never-attempted companies as "done, no match", and a LinkedIn special-character trap in headquarters extraction (deliberately no longer taken from LinkedIn because of this — headquarters now comes reliably from Wikidata).',
    ],
  },
  {
    version: '3.27.0',
    date: '2026-07-03',
    changes: [
      'The three old separate background bridges (files_bridge.py, notes_bridge.py, calls_bridge.py) have been removed — the new JobTracker Agent has been running in production as a full replacement for several days and was verified live against the real instance (health check, startup check, a real backup round-trip) before the old scripts were shut down and deleted. Documentation (README, architecture, project status) updated accordingly.',
    ],
  },
  {
    version: '3.26.1',
    date: '2026-07-03',
    changes: [
      'Fix: /api/startup-check crashed with a 500 as soon as local file sync was enabled — the code read the wrong field name (FilesConfig.folder instead of .folder_path). Found and fixed while verifying the new agent live; previously untested, now backed by 7 new tests.',
    ],
  },
  {
    version: '3.26.0',
    date: '2026-07-03',
    changes: [
      'JobTracker Agent: the three separate background bridges (files, notes, calls) are replaced by a single, actually installable background service — with Bearer-token auth instead of open ports, packaged as a .app/.dmg with a menu-bar icon and automatic self-registration as a startup item (no more manual terminal window). New "Agent" tab in Settings for connecting (paste token, live status per module). The architecture is deliberately cross-platform (macOS now, Windows later via the same provider interface). The old three bridge scripts still run in parallel as a transition.',
    ],
  },
  {
    version: '3.25.0',
    date: '2026-07-02',
    changes: [
      'New manual restore feature in Settings → Backup: pick and restore any backup file (.zip or .db) via a native file picker — works regardless of whether automatic backup is enabled or a backup folder is even configured. Handy e.g. for loading a production backup deliberately into the new isolated test environment.',
    ],
  },
  {
    version: '3.24.1',
    date: '2026-07-02',
    changes: [
      'New isolated 1:1 test environment (docker-compose.test.yml): its own empty database, its own volume, its own ports (GUI on :3001, API on :8001), completely separate from the production instance. Fully usable via the GUI as normal, but clearly marked with a red "TEST ENVIRONMENT" banner at the top so it\'s never confused with real data — intended e.g. for safely testing a restore from a production backup.',
    ],
  },
  {
    version: '3.24.0',
    date: '2026-07-02',
    changes: [
      'Closed a backup/restore gap: the encryption key (fernet.key) for stored API keys/passwords lived outside the database and wasn\'t being backed up — after a restore onto a new machine/fresh volume, encrypted fields (AI key, iCloud password, Google client secret, Maps key) would have become permanently undecryptable. Backups are now a zip bundle of the database and the key; restore brings both back together. Older plain .db backups remain restorable. Note: the host-side files_bridge process needs to be manually restarted once after this update.',
    ],
  },
  {
    version: '3.23.0',
    date: '2026-07-02',
    changes: [
      'Fix (critical): when merging applications, and during automatic cleanup of application duplicates, timeline entries (events) belonging to the removed application weren\'t reassigned to the surviving application — instead, an ORM cascade accidentally deleted them along with it on delete. Cause: the assignment happened via the raw foreign-key field instead of the relationship API, leaving the internal object cache stale. The same problem occurred for applications/contacts during company merges (the assignment was lost when the losing company was deleted). Both spots are now correct — the bug was found by new tests for Phase 3 of the test concept before it could cause further damage.',
      'Test concept Phase 3 complete: L1/L2 tests for merge (applications/contacts/companies) as well as for the previously untested cleanup duplicate finders (applications, contacts) and the /cleanup endpoints including scope filtering.',
    ],
  },
  {
    version: '3.22.4',
    date: '2026-07-02',
    changes: [
      'Test concept Phase 2 complete: round-trip tests for the Fernet encryption of stored API keys (encrypt/decrypt, automatic key generation, error cases for a broken/wrong key). This backs all three "sensitive" areas from the test concept (dedup, status logic, crypto) with L0 unit tests.',
    ],
  },
  {
    version: '3.22.3',
    date: '2026-07-02',
    changes: [
      'Added a LICENSE file (Business Source License 1.1): free use for private, non-commercial purposes, commercial use requires a separate license. Automatically converts to the Apache License 2.0 on 2030-07-02.',
    ],
  },
  {
    version: '3.22.2',
    date: '2026-07-02',
    changes: [
      'Security hardening ahead of the planned public release: the self-hosted CI jobs (Deploy, failure notification) that run on this Mac are now explicitly restricted to push events and can never again be triggered by a pull_request (even from a fork). Test/build jobs for pull requests continue to run as usual on GitHub-hosted runners.',
    ],
  },
  {
    version: '3.22.1',
    date: '2026-07-02',
    changes: [
      'Security cleanup: an accidentally committed DB backup with real contact and application data was completely removed from the git history (a prerequisite for a planned public release of the repo). The CI deploy step now uses "fetch + reset --hard" instead of "git pull", so force-pushes like this one no longer break auto-deploy.',
    ],
  },
  {
    version: '3.22.0',
    date: '2026-07-02',
    changes: [
      'Location autocomplete now optionally runs via Google Maps (Places API) instead of just OpenStreetMap — including specific places/POIs (e.g. office locations), not just city names. New "Maps" settings tab for entering a Google Maps API key (stored encrypted, never leaves the server). Without a key, location search continues to work as before via Nominatim/OpenStreetMap.',
    ],
  },
  {
    version: '3.21.2',
    date: '2026-07-02',
    changes: [
      'Fix: the location was visible in the overview tab, but not on the Kanban card — the applications-list response schema (which also populates the Kanban cards) didn\'t declare the "ort" field, so it got filtered out of the response even though it was set in the database.',
    ],
  },
  {
    version: '3.21.1',
    date: '2026-07-02',
    changes: [
      'An application\'s location is now also shown on the Kanban card, bottom right — as a link that opens the address directly in Google Maps.',
    ],
  },
  {
    version: '3.21.0',
    date: '2026-07-02',
    changes: [
      'New "location" field on applications (optional, visible in the overview tab). Manual entry with autocomplete via a free maps API (OpenStreetMap/Nominatim, no API key needed). Automatically filled in from the job posting during LinkedIn sync, without overwriting a location already set manually.',
    ],
  },
  {
    version: '3.20.0',
    date: '2026-07-02',
    changes: [
      'Removed the separate company filter (dropdown button) in the applications and contacts views. Instead, the normal search fields now offer company autocomplete: matching companies appear as you type, picking one fills in the search text directly. Jumping from a company to its applications/contacts (company view) still works, but now simply sets the search text instead of a separate filter.',
    ],
  },
  {
    version: '3.19.2',
    date: '2026-07-01',
    changes: [
      'iCloud contacts sync (follow-up to v3.19.1): a domain match of the email address against the company website alone was enough to import contacts — even when no application existed for that company at all (live: 32 Contoso contacts imported despite 0 applications to Contoso; the CompanyProfile was just a data leftover). A domain match now only counts when the company is actually linked to at least one application.',
    ],
  },
  {
    version: '3.19.1',
    date: '2026-07-01',
    changes: [
      'iCloud contacts sync sometimes imported hundreds of irrelevant contacts (592 live, 272 of them with company "Contoso GmbH" alone) — a plain text match of a vCard\'s ORG field against the name of a known company was enough to import practically the entire address book of a former employer, regardless of any real connection to an application. A company-name match alone no longer counts — in addition, either the contact\'s email domain must match the company website, or the contact must actually be mentioned in an application or linked via company text.',
    ],
  },
  {
    version: '3.19.0',
    date: '2026-07-01',
    changes: [
      'When manually searching for and assigning sync matches to an application ("manual assign"), you can now check multiple entries and import them together in one step, instead of having to click them one at a time. Conflicts on individual entries (already linked to another application) are skipped and reported, the rest is still imported.',
    ],
  },
  {
    version: '3.18.2',
    date: '2026-07-01',
    changes: [
      'Cleanup wrongly detected subsidiaries as duplicates when they share the parent\'s website domain (e.g. "Contoso Digital Industries Software" under contoso.com) — even when the parent-subsidiary relationship was already set up. Already-linked pairs are now ignored. For still-unlinked duplicates, there\'s now a new "assign as subsidiary" option alongside merging.',
    ],
  },
  {
    version: '3.18.1',
    date: '2026-07-01',
    changes: [
      'Company sync (for good this time): every click on "Sync" kept finding the same handful of small/obscure companies with no web presence, because "missing description" still counted as an unlimited retry reason (the same bug type as the logo fix in v3.17.3, just reintroduced elsewhere). A "done" profile is now never automatically reset to "pending" again — neither for a missing logo nor a missing description. "Sync" now only processes genuinely new companies, "re-sync" remains the deliberate way to retry.',
    ],
  },
  {
    version: '3.18.0',
    date: '2026-07-01',
    changes: [
      'New analytics: the biggest pipeline bottleneck is now explicitly highlighted (the stage with the largest absolute application loss, not just the lowest rate — avoids wrong conclusions from small sample sizes). New "conversion per transition" chart shows the rate for each individual pipeline step.',
      'Success by company type (startup/enterprise/SME/consulting/…) and company size as their own analytics — interview and offer rate per group.',
      'Success by role category: rough classification from the job title via keyword heuristics (leadership/senior/other), since there\'s no structured field for "type of role".',
    ],
  },
  {
    version: '3.17.5',
    date: '2026-07-01',
    changes: [
      'Cleanup in the calendar view now only handles real calendar entries (same definition as the calendar view itself: interviews/appointments or Google/iCloud calendar source) instead of all timeline objects (mails, calls, notes). Verified live: 33 → 15 duplicates in the calendar scope, the remaining 18 were mail/call duplicates and don\'t belong there.',
    ],
  },
  {
    version: '3.17.4',
    date: '2026-07-01',
    changes: [
      'Cleanup (calendar/timeline): didn\'t find real duplicates when the same synced appointment/call/mail was saved with a different type across multiple sync runs (e.g. "status" and "interview" for the same calendar appointment). Found 33 such duplicates live that had previously been completely missed. The more meaningful type (interview/appointment/call) is now preferentially kept when merging.',
    ],
  },
  {
    version: '3.17.3',
    date: '2026-07-01',
    changes: [
      'Company sync: companies without a Clearbit logo (mostly small recruiting agencies — 101 of 158 affected) were repeatedly detected as "incomplete" and re-synced on every sync click, even though the list already showed them as "synced". Logo lookup is deterministic — a logo that\'s missing once stays missing. Only a missing company description now triggers a retry.',
    ],
  },
  {
    version: '3.17.2',
    date: '2026-07-01',
    changes: [
      'CI: test results are now visible directly in the GitHub Actions run summary (pass/fail counts + names of failed tests), without having to expand the logs — for backend (pytest) and frontend (vitest), both via JUnit XML.',
    ],
  },
  {
    version: '3.17.1',
    date: '2026-07-01',
    changes: [
      'Fix: pytest failed in real CI ("No module named app") — tested locally with `python -m pytest`, which automatically adds the working directory to sys.path, but CI calls bare `pytest`. Added `pythonpath = .` to pytest.ini, verified against the exact CI invocation in the container.',
    ],
  },
  {
    version: '3.17.0',
    date: '2026-07-01',
    changes: [
      'Implemented test concept Phase 1: pytest scaffolding with test-DB isolation, factories (application/contact/company/event), 37 backend tests (unit/component/API), and a Vitest setup with the first frontend component tests. Extended the CI PR gate — runs in under 6 seconds.',
    ],
  },
  {
    version: '3.16.2',
    date: '2026-07-01',
    changes: [
      'CI: the deploy notification on the Mac now shows the full app version (e.g. "v3.16.2") instead of just the build number — matching what\'s shown top-left in the app.',
    ],
  },
  {
    version: '3.16.1',
    date: '2026-07-01',
    changes: [
      'Gmail/iCloud sync for an application found no mails when the auto-enriched company website had the wrong domain (e.g. hahn-schickard.com instead of .de) — the search filtered exclusively on that one domain. Confirmed contact email addresses of the application now also feed into the domain search, independent of the (possibly wrong) company enrichment.',
    ],
  },
  {
    version: '3.16.0',
    date: '2026-07-01',
    changes: [
      'Company sync: fix for v3.15.8 — the auto-continue poller after a sync batch ignored the selection and kept syncing all pending companies anyway. Scoped runs now stop after their own batch.',
      'LinkedIn setup was duplicated (sync dropdown and options menu) — removed from the sync dropdown, now only in Settings under "LinkedIn".',
      'The cleanup function is now context-sensitive: the button only shows and cleans up the category of the current view (applications/contacts/companies/calendar) instead of always everything. New: company duplicates are detected by website domain (the name field is already unique in the DB) and merged via the existing merge logic. Application matching now uses the same normalized company/role detection as the rest of the app; contact matching additionally considers the company so same-name-but-different-person contacts are no longer wrongly merged.',
    ],
  },
  {
    version: '3.15.8',
    date: '2026-07-01',
    changes: [
      'Companies: sync, re-sync, and "link contacts" now respect the selection — with companies selected, all three actions only run for the selection instead of the whole list. Without a selection, behavior is unchanged (all companies).',
    ],
  },
  {
    version: '3.15.7',
    date: '2026-06-30',
    changes: [
      'Company modal: changes (edit, logo, assign contacts) were missing an onSaved callback — the companies list and application views only showed changes after a manual reload. Fixed.',
    ],
  },
  {
    version: '3.15.6',
    date: '2026-06-30',
    changes: [
      'LinkedIn import: found and fixed the root cause — LinkedIn now hashes all CSS class names, so every existing company-name selector was hitting nothing. Company name is now read via stable structural signals (link to the company page in the posting header, page-title pattern) instead of class names — verified live on a real headhunter posting (BLACKBULL INTERNATIONAL GmbH correctly recognized).',
    ],
  },
  {
    version: '3.15.5',
    date: '2026-06-30',
    changes: [
      'LinkedIn import: fallback for anonymized/"confidential" job postings — when the company isn\'t visible in the page header, the "hiring team"/recruiter section is also searched for the associated company name (headhunter name) before the field is left empty.',
    ],
  },
  {
    version: '3.15.4',
    date: '2026-06-30',
    changes: [
      'LinkedIn import: the AI prompt now recognizes headhunter postings from clear signals (e.g. "on behalf of", "Executive Search" in the company name, an anonymized client description) and fills "target company" with the available description instead of leaving it empty or hiding it in the comment.',
    ],
  },
  {
    version: '3.15.3',
    date: '2026-06-30',
    changes: [
      'LinkedIn import: company name is now read structurally from the job-posting header instead of guessed by the AI from the description text — fixes a missing company for headhunter postings that anonymize the client in the text ("A publicly traded technology group…").',
    ],
  },
  {
    version: '3.15.2',
    date: '2026-06-30',
    changes: [
      'LinkedIn import: the company is now automatically matched against existing company profiles or cleanly created — on creation, the company-data fetch (description, logo, industry, location) runs once in the background, same as the regular company sync.',
    ],
  },
  {
    version: '3.15.1',
    date: '2026-06-30',
    changes: [
      'Fixed LinkedIn import: instead of manually pasting text, just enter the link to the job posting — the page is loaded automatically via the existing LinkedIn session, and the AI extracts all fields from it.',
    ],
  },
  {
    version: '3.15.0',
    date: '2026-06-30',
    changes: [
      'Completely removed the job-search feature (tab, job-board settings, backend router, data model). Was no longer an actively used feature.',
      'New application: the "New" button is now a dropdown with "create manually" and "import from LinkedIn" — for LinkedIn import, the copied job-posting text is analyzed by AI and company, role, source, headhunter flag, and comment are automatically pre-filled.',
    ],
  },
  {
    version: '3.14.52',
    date: '2026-06-30',
    changes: [
      'AI batch run ("AI assess"): now shows live progress in the button ("AI: 3/27") instead of just a static "AI running…" — the backend streams progress via SSE, the Kanban view updates after every assessment.',
    ],
  },
  {
    version: '3.14.51',
    date: '2026-06-30',
    changes: [
      'AI settings: model-selection chips for Groq, Gemini, Anthropic, OpenAI had so far only been implemented in the unused AiSettingsModal component — App.tsx actually renders SettingsModal. Chip selection is now built in there, dead AiSettingsModal.tsx removed.',
      'AI assessment in the application modal: the Kanban view and applications list now update immediately after "reassess" (onSaved() wasn\'t being called).',
    ],
  },
  {
    version: '3.14.50',
    date: '2026-06-30',
    changes: [
      'AI settings: model-selection chips for Groq, Gemini, Anthropic, OpenAI — models now live directly in the provider array instead of a separate dictionary (more robust lookup).',
    ],
  },
  {
    version: '3.14.49',
    date: '2026-06-30',
    changes: [
      'AI: models that don\'t support JSON mode or don\'t exist now return a clear error message (400) instead of a raw 502 stack trace.',
    ],
  },
  {
    version: '3.14.48',
    date: '2026-06-30',
    changes: [
      'AI assessment: the UI refresh after "reassess" now works — fields are written directly from the API response into local state, no more second GET request.',
    ],
  },
  {
    version: '3.14.47',
    date: '2026-06-30',
    changes: [
      'AI settings: model-selection fix — replaced an IIFE pattern with clean variables (providerModels/isKnownModel).',
    ],
  },
  {
    version: '3.14.46',
    date: '2026-06-30',
    changes: [
      'AI options: rate-limit and auth errors are now shown in an understandable way (no longer as a raw JSON blob).',
    ],
  },
  {
    version: '3.14.45',
    date: '2026-06-30',
    changes: [
      'AI batch: 5-second pause between requests for Gemini/Groq — prevents rate-limit errors. Each application is saved right after being assessed.',
      'Rate-limit errors (429) are now shown understandably in the modal instead of as a 502.',
    ],
  },
  {
    version: '3.14.44',
    date: '2026-06-30',
    changes: [
      'AI settings: chip-based model selection for Groq (5 models), Gemini (5 models), Anthropic, and OpenAI — same as Ollama. The selected model is shown below as an ID.',
    ],
  },
  {
    version: '3.14.43',
    date: '2026-06-30',
    changes: [
      'AI assessment: new "reasoning" field explains why the success chance was rated this way (concrete facts from the timeline).',
      'AI rejection analysis: called explicitly for rejected applications → analyzes rejection reasons + improvement suggestions for future applications.',
      'Batch assessment skips rejected applications (main_status=rejected).',
    ],
  },
  {
    version: '3.14.42',
    date: '2026-06-30',
    changes: [
      'AI prompt: today\'s date is now passed explicitly. Made-up dates/weekdays are forbidden. next_step now requires 2–4 sentences with a situation summary + recommended action.',
    ],
  },
  {
    version: '3.14.41',
    date: '2026-06-30',
    changes: [
      'AI assessment: timeline events are now passed to the AI in full (untruncated) — email content, calendar notes, etc.',
      'AI assessment: success chance is now explicitly shown as text ("High / Medium / Low") in the table, Kanban, and modal.',
    ],
  },
  {
    version: '3.14.40',
    date: '2026-06-30',
    changes: [
      'AI assessment: the prompt now writes next_step as an imperative action instruction with real numbers. Forbidden: copying status labels, repeating the email subject, vague phrases.',
      'AI logging: every AI request and response is logged under category "ai" (docker logs + Seq).',
    ],
  },
  {
    version: '3.14.39',
    date: '2026-06-30',
    changes: [
      'AI assessment: now evaluates all timeline events in full (chronologically, including subject and content). Interview notes and the comment field are factored in too.',
    ],
  },
  {
    version: '3.14.38',
    date: '2026-06-30',
    changes: [
      'AI assessment: reworked the prompt — computes real day counts, evaluates process depth (number of interviews) and the concrete timeline. Placement: at the bottom of the overview in the modal (with date and "reassess"), as a color dot + text in table/Kanban.',
    ],
  },
  {
    version: '3.14.37',
    date: '2026-06-30',
    changes: [
      'AI assessment: color (green/yellow/red) and next step per application based on status and timeline. Updates automatically after a targeted sync. "AI assess" button for all active applications in the header; "AI" button per application in the modal.',
    ],
  },
  {
    version: '3.14.36',
    date: '2026-06-30',
    changes: [
      'The company name on applications now comes from the company master record (name_display) when linked — in table, Kanban, application modal, review, and contact views.',
    ],
  },
  {
    version: '3.14.35',
    date: '2026-06-30',
    changes: [
      'iCloud contact sync: now only imports relevant contacts — name/email must appear in application events or fields, or the company must match an application or a company profile. Address-book contacts with no job connection are skipped.',
    ],
  },
  {
    version: '3.14.34',
    date: '2026-06-30',
    changes: [
      'Companies: "select all" checkbox (filter-aware), "delete X" button, count/selection in the footer — same as contacts. Contacts: "select all" now respects active filters.',
    ],
  },
  {
    version: '3.14.33',
    date: '2026-06-30',
    changes: [
      'Contacts: filter "has applications" (all / yes / no). Companies: filters "has applications" and "has contacts" — client-side, no backend request.',
    ],
  },
  {
    version: '3.14.32',
    date: '2026-06-30',
    changes: [
      'Company picker when manually creating applications and contacts: company dropdown with search and a "create new" option — same as edit mode. The contacts tab in a company profile now has a mode switch "create new" / "assign existing".',
    ],
  },
  {
    version: '3.14.31',
    date: '2026-06-30',
    changes: [
      'Company sync: Wikipedia REST API as a fallback when DDG returns nothing. Logo fallback via Clearbit (domain-based). sync_source shows which source was used.',
    ],
  },
  {
    version: '3.14.30',
    date: '2026-06-30',
    changes: [
      'Cancel button for company sync and contact linking — aborts gracefully after the current entry. Contact linking now shows a progress counter (x/total).',
    ],
  },
  {
    version: '3.14.29',
    date: '2026-06-30',
    changes: [
      'Company sync: replaced Wikidata with the DuckDuckGo Instant Answer API — no rate limit, no API key, no waiting. Provides description, logo, HQ, founding year, employee count, and industry from Wikipedia infoboxes.',
    ],
  },
  {
    version: '3.14.28',
    date: '2026-06-30',
    changes: [
      'Company sync: retry with exponential backoff on Wikidata 429/503 (up to 4 attempts, respects Retry-After). Increased search-API spacing to 1s, SPARQL batch pause to 5s.',
    ],
  },
  {
    version: '3.14.27',
    date: '2026-06-30',
    changes: [
      'Company sync: batch SPARQL — all Q-IDs are first collected via the search API (0.3s spacing), then queried in a single SPARQL request (up to 40 companies per query). Logo downloads run in parallel (max 3 at once). Fixes "too many requests" on larger batches.',
    ],
  },
  {
    version: '3.14.26',
    date: '2026-06-30',
    changes: [
      'Company sync: the logo is now loaded directly from Wikidata (P154) and stored as base64 — no more manual upload needed for known companies.',
    ],
  },
  {
    version: '3.14.25',
    date: '2026-06-30',
    changes: [
      'Company sync: removed AI — data now comes from Wikidata (search API + SPARQL). Fields: HQ city/country, founding year, employee count, website, LinkedIn URL, industry, description.',
    ],
  },
  {
    version: '3.14.24',
    date: '2026-06-30',
    changes: [
      'Seq log: source field per sync source — filter in Seq by source = linkedin or source = targeted.',
    ],
  },
  {
    version: '3.14.23',
    date: '2026-06-30',
    changes: [
      'LinkedIn sync: application date is backfilled for existing apps if not yet set.',
    ],
  },
  {
    version: '3.14.22',
    date: '2026-06-30',
    changes: [
      'Fix: LI sync extracts the job ID from the scraped job-posting URL (job["stellenanzeige_url"]) — job["id"] was previously always empty, so URL-based matching never fired.',
    ],
  },
  {
    version: '3.14.21',
    date: '2026-06-30',
    changes: [
      'Individual LinkedIn sync: scrapes category by category and matches immediately by LI job ID (from linkedin_job_id or stellenanzeige_url) or company+role — stops after the first match without processing all other jobs.',
    ],
  },
  {
    version: '3.14.20',
    date: '2026-06-30',
    changes: [
      'LinkedIn sync: the application URL (stellenanzeige_url) is used as an LI job-ID source — matches even when linkedin_job_id isn\'t set yet.',
      'Per-application LinkedIn sync: stops as soon as the target application is found, skipping all other jobs.',
    ],
  },
  {
    version: '3.14.19',
    date: '2026-06-30',
    changes: [
      'Per-application sync now also includes LinkedIn — LI runs in parallel, progress bar and suggestion counter appear in the modal.',
    ],
  },
  {
    version: '3.14.18',
    date: '2026-06-30',
    changes: [
      'LinkedIn sync: removed the debug Excel — all sync details (match reason, category counts, pagination, errors) now flow into the structured log (Seq, category: sync).',
    ],
  },
  {
    version: '3.14.17',
    date: '2026-06-30',
    changes: [
      'LinkedIn sync: match reason (job_id / company+role / alias / new) visible per entry in the log.',
      'When a status suggestion is skipped (already pending / already reviewed), it now shows in the log.',
    ],
  },
  {
    version: '3.14.16',
    date: '2026-06-30',
    changes: [
      'Application: company name is no longer a free-text field — only assignment from existing company profiles or creating a new one (same as contacts).',
    ],
  },
  {
    version: '3.14.15',
    date: '2026-06-29',
    changes: [
      'Fix: company merge now updates app.firma, zielfirma_bei_hh, and contact.firma to the winner\'s name.',
    ],
  },
  {
    version: '3.14.14',
    date: '2026-06-29',
    changes: [
      'Contacts: separate first-/last-name fields — sync recognizes "Mehra, Malvika" and "Malvika Mehra" as the same person.',
      'Contacts: edit modal (click a row) — all fields editable, same as company profiles.',
      'Contacts: the application form shows first/last name as separate fields.',
    ],
  },
  {
    version: '3.14.13',
    date: '2026-06-29',
    changes: [
      'Sync: domain-based matching (mail/calendar) instead of a contact index — date >= application date.',
      'Sync: contact sync now runs after mail/calendar, so contacts get found in new events.',
      'Sync: iCloud Notes — no more "recent 30" fallback, text matching only.',
      'Contacts: email is now a required field when creating and editing.',
    ],
  },
  {
    version: '3.14.12',
    date: '2026-06-29',
    changes: [
      'Application modal: contacts can now either be created fresh or assigned from existing contacts.',
      'Live search in "assign existing" mode filters immediately by name, email, or company.',
    ],
  },
  {
    version: '3.14.11',
    date: '2026-06-29',
    changes: [
      'Structured logging: Loguru replaces stdlib logging — JSON to stdout, all logs forwarded to Seq.',
      'Categories: sync, ai, backup, app — filterable in Seq by category, level, and time range.',
      'The Seq log viewer runs at http://localhost:8088',
    ],
  },
  {
    version: '3.14.10',
    date: '2026-06-29',
    changes: [
      'Detailed sync logging: all sync sources (Gmail, GCal, iCloud Mail, iCloud Cal, Notes, Reminders) now log per-item decisions to the Docker log (DEBUG level).',
      'Format: [SYNC #<id> <source>] <item-id> → SKIP/CREATED/pending with subject, sender, and reason.',
    ],
  },
  {
    version: '3.14.9',
    date: '2026-06-29',
    changes: [
      'Startup check: when the app loads, all local bridges (Files, Notes, Calls) and connections (Google, iCloud, AI, local files) are checked.',
      'Missing/unreachable services appear as a yellow banner with details — expandable on click, retriable, and dismissible.',
    ],
  },
  {
    version: '3.14.8',
    date: '2026-06-29',
    changes: [
      'Sync menu: new entry "clear sync events" — removes all automatically generated timeline entries for an application without starting a new sync.',
    ],
  },
  {
    version: '3.14.7',
    date: '2026-06-29',
    changes: [
      'Targeted sync (Gmail, iCloud Mail, iCloud Cal) no longer falls back to the company name when no contacts are linked — eliminates false-positive mails/appointments from ambiguous names (e.g. "HERE" matching "there").',
      'iCloud Mail: search is now address-based (contact domains/emails instead of company name).',
      'iCloud Cal: matching is now via organizer/attendee email instead of a text search in the title.',
    ],
  },
  {
    version: '3.14.6',
    date: '2026-06-29',
    changes: [
      'Removed AI from sync entirely: mails, calendar entries, iCloud notes, and reminders are now classified purely deterministically (regex patterns for type, subject line as title).',
      'No more AI fallback for multiple matched applications — the first match is used.',
    ],
  },
  {
    version: '3.14.5',
    date: '2026-06-29',
    changes: [
      'Radically simplified Gmail/calendar matching: mails and appointments are now matched only by the email addresses of linked contacts (exact address or company domain) — no more company-name substring matching, which caused false positives like "there" → HERE.',
      'The global Gmail sync now uses a domain-based search filter instead of the company name.',
      'A new contact is automatically created when a new address from a known company domain is detected.',
    ],
  },
  {
    version: '3.14.4',
    date: '2026-06-29',
    changes: [
      'Gmail: expired/revoked OAuth tokens are now detected (invalid_grant). Tokens are automatically deleted and a clear message with a hint to reconnect appears.',
    ],
  },
  {
    version: '3.14.3',
    date: '2026-06-29',
    changes: [
      'Sync change indicator: after a sync, not only changed applications are marked, but the specific fields are also highlighted (amber background + dot for status, comment, source, interview notes, job posting, etc.).',
      'The field highlights disappear as soon as the application is opened.',
    ],
  },
  {
    version: '3.14.2',
    date: '2026-06-29',
    changes: [
      'Kanban layout: columns now automatically spread across the full width — few columns fill the screen evenly, many columns scroll horizontally.',
    ],
  },
  {
    version: '3.14.1',
    date: '2026-06-26',
    changes: [
      'Fixed LinkedIn message matching: contact names (from the database) are now used as the primary matching signal — LinkedIn shows people\'s names, not company names, in the sidebar.',
      'Fallback: company name in the message-preview text (≥ 5 characters) for recruiters not yet known.',
      'Threads are only opened on an actual match, no more blindly opening every conversation.',
    ],
  },
  {
    version: '3.14.0',
    date: '2026-06-26',
    changes: [
      'Integrated LinkedIn sync into the normal sync button — now runs automatically with all other sources.',
      'New data source "linkedin_msg": LinkedIn messages are scraped and linked as timeline events (type: mail).',
      '2FA entry directly in the sync progress overlay, no separate dialog.',
      '"Set up LinkedIn" in the sync dropdown opens the configuration (credentials, session reset).',
    ],
  },
  {
    version: '3.13.1',
    date: '2026-06-26',
    changes: [
      'PDF export: calendar entries (Google/iCloud) now fully included in the appointments overview — even when the global sync didn\'t classify them as "interview".',
    ],
  },
  {
    version: '3.13.0',
    date: '2026-06-26',
    changes: [
      'Sync indicator: new or changed applications get marked with a pulsing dot after every sync.',
      'Automatically opens the review dialog when manual tasks come up after a sync.',
      'Review counter: now updates after every kind of sync (per-application, company sync) + 30s polling.',
    ],
  },
  {
    version: '3.12.0',
    date: '2026-06-26',
    changes: [
      'Application modal: tabs Overview / Timeline / Attachments / Contacts (same as the company modal).',
      'Timeline tab: filter by time range (1M/3M/6M/1Y) and event type (mail, calendar, interview …).',
      'Attachments and contacts moved into their own tabs.',
      'Wider modal (max-w-3xl) for more room.',
    ],
  },
  {
    version: '3.11.0',
    date: '2026-06-26',
    changes: [
      'Contact sync: all company contacts from the machine are imported and shown in the company\'s contacts tab.',
      'Application linking only happens when a contact is explicitly mentioned in mails, calendar, or application notes.',
    ],
  },
  {
    version: '3.10.0',
    date: '2026-06-26',
    changes: [
      'Company sync: sync actions combined into a dropdown.',
      'Sync: only updates pending companies and ones with empty fields.',
      'Re-sync: resets all companies and re-fetches all data.',
      '"Reset failed" is now part of the sync dropdown.',
    ],
  },
  {
    version: '3.9.0',
    date: '2026-06-26',
    changes: [
      'The company filter in applications/contacts now also includes subsidiaries.',
    ],
  },
  {
    version: '3.8.0',
    date: '2026-06-26',
    changes: [
      'New: bulk-assign parent company in the companies list — select multiple companies, search for and assign a parent company.',
    ],
  },
  {
    version: '3.7.0',
    date: '2026-06-26',
    changes: [
      'New: hierarchical company structure — link parent companies and subsidiaries.',
      'Company profile: assign a parent company in edit mode via search (cycle detection).',
      'Company profile: shows the parent company and subsidiaries as clickable links.',
      'Companies list: a small "↑ parent name" hint on subsidiaries.',
    ],
  },
  {
    version: '3.6.0',
    date: '2026-06-26',
    changes: [
      'New: company filter with autocomplete in the applications and contacts views.',
      'New: companies list → applications/contacts opens the company filter directly in the target view.',
      'New: manually assign contacts to a company — from the contacts list and from the company modal.',
      'Fix: missing links to the company in the contacts list.',
      'Fix: contacts are automatically linked to company profiles on backend startup.',
    ],
  },
  {
    version: '3.5.0',
    date: '2026-06-26',
    changes: [
      'New: company modal with tabs (profile / applications / contacts) — contacts from linked applications.',
      'New: edit companies (display name, industry, type, employees, location, website, description).',
      'New: merge companies — same as applications/contacts, field-by-field selection.',
      'New: contact count in the companies list, multi-select for merge.',
    ],
  },
  {
    version: '3.4.1',
    date: '2026-06-26',
    changes: [
      'New: Logo.dev as the primary logo source (Settings → Logos). Provides real logos including headhunter agencies; Google Favicons remains a fallback.',
      'New: company logos in the applications table and Kanban board.',
      'Fix: company logos in the companies list — Clearbit (shut down) replaced with Google Favicons.',
    ],
  },
  {
    version: '3.3.8',
    date: '2026-06-25',
    changes: [
      'New: pick the backup folder via a folder picker (native macOS dialog).',
      'New: a restore button per backup — restores the entire database from a snapshot.',
    ],
  },
  {
    version: '3.3.7',
    date: '2026-06-25',
    changes: [
      'New: company logos in the companies list — loaded automatically via Clearbit, initials as a fallback.',
      'Fix: the company-profile button in the application modal was never clickable (company_profile_id was missing from the detail endpoint).',
      'Fix: "refresh company data" stayed permanently disabled after the first sync.',
    ],
  },
  {
    version: '3.3.6',
    date: '2026-06-25',
    changes: [
      'Fix: LI sync session detection — now uses /feed instead of jobs-tracker as the check URL, so expired sessions are reliably detected and re-logged-in.',
      'UX: the 2FA dialog now explains app confirmation as the primary option; code entry remains as a fallback.',
    ],
  },
  {
    version: '3.3.5',
    date: '2026-06-25',
    changes: [
      'Fix: the status badge on the company profile now uses the same StatusBadge component as the applications overview — identical colors and labels.',
    ],
  },
  {
    version: '3.3.4',
    date: '2026-06-25',
    changes: [
      'Fix: the LinkedIn button at the bottom of the app was visible — now hidden when it\'s acting as a pure dropdown trigger.',
    ],
  },
  {
    version: '3.3.3',
    date: '2026-06-25',
    changes: [
      'Company profile: the applications list now shows role, application date, and status — the company name was removed (redundant).',
    ],
  },
  {
    version: '3.3.2',
    date: '2026-06-25',
    changes: [
      'UX: integrated LinkedIn sync into the sync dropdown — no more separate button in the header.',
      'UX: combined Excel export, PDF export, and Excel import into one "import/export" dropdown.',
    ],
  },
  {
    version: '3.3.1',
    date: '2026-06-25',
    changes: [
      'Moved company sync from Analytics to the companies page — sync button, progress bar, and error reset directly in the companies table.',
    ],
  },
  {
    version: '3.3.0',
    date: '2026-06-25',
    changes: [
      'New: companies page — all company profiles in a table with industry, type, size, location, and sync status.',
      'New: company profile modal with all AI-synced data (description, website, LinkedIn, founding year, employee count) and linked applications.',
      'Company names clickable everywhere: table, Kanban cards, and the application modal now open the company profile.',
    ],
  },
  {
    version: '3.2.10',
    date: '2026-06-25',
    changes: [
      'Fix: LinkedIn sync now correctly detects expired sessions — when LI redirects to the home page instead of /login or /authwall, it now still logs back in.',
    ],
  },
  {
    version: '3.2.9',
    date: '2026-06-25',
    changes: [
      'Fix: ported the Ollama model picker, auto-save, and the host.docker.internal URL into the AI/API settings (SettingsModal) — previously only implemented in the standalone AiSettingsModal.',
      'Ollama: model selection as chips (installed) + a download list with a progress indicator. No more global save button.',
    ],
  },
  {
    version: '3.2.8',
    date: '2026-06-25',
    changes: [
      'UX: AI settings save automatically — provider switch, model selection, toggles, and text fields (onBlur) trigger an immediate save.',
      'No more global save button; the API key has its own OK button. Save status shown as an icon in the header.',
    ],
  },
  {
    version: '3.2.7',
    date: '2026-06-25',
    changes: [
      'Fix: the Groq API key is no longer injected as a fallback into Ollama test requests — switching providers now tests the correct one.',
      'Fix: the Ollama URL default is now host.docker.internal:11434 (instead of localhost, which isn\'t reachable from the container).',
      'UX: the save confirmation shows the saved provider + model, errors are shown visibly.',
    ],
  },
  {
    version: '3.2.6',
    date: '2026-06-25',
    changes: [
      'Ollama model picker: installed models as clickable chips, popular models with a download button and progress bar.',
      'New: GET /api/settings/ollama/models (model list) + GET /api/settings/ollama/pull (SSE stream for download progress).',
    ],
  },
  {
    version: '3.2.5',
    date: '2026-06-25',
    changes: [
      'Company-data sync now runs via AI (instead of LinkedIn scraping) — no login needed, works with any configured AI provider.',
      'Live progress: a progress bar and the company currently being synced are shown during the sync (polling every 1.5s).',
    ],
  },
  {
    version: '3.2.4',
    date: '2026-06-25',
    changes: [
      'Fix: "last update" now always shows the date of the most recent timeline entry — no longer the date of the last edit.',
    ],
  },
  {
    version: '3.2.3',
    date: '2026-06-25',
    changes: [
      'Fix: company-data sync — browser flags (--no-sandbox), structure-based LI company detection instead of hashed classes, login fallback.',
      'Company-data sync: lock reset before every run (no more "already running"), a "reset failed" button in the analytics tab.',
    ],
  },
  {
    version: '3.2.2',
    date: '2026-06-25',
    changes: [
      'Removed the interview rate from the applications page — now lives in the analytics tab.',
    ],
  },
  {
    version: '3.2.1',
    date: '2026-06-25',
    changes: [
      'Backfill: on container start, CompanyProfile entries (pending) are automatically created for all existing applications — company names get deduplicated.',
    ],
  },
  {
    version: '3.2.0',
    date: '2026-06-25',
    changes: [
      'New: analytics tab — KPI tiles, conversion funnel, pipeline donut, source bars, HH-vs-direct comparison, applications over time, rejections by phase.',
      'Backend: GET /api/analytics/summary — computes all KPIs, funnel, monthly distribution, and company-profile sync status directly from the DB.',
      'Company-data sync: POST /api/sync/company/run — starts LinkedIn scraping for pending CompanyProfiles in the background (max 10 per run).',
      'Auto-CompanyProfile: when creating/updating applications, company names are automatically normalized and entered into company_profiles (sync_status=pending).',
    ],
  },
  {
    version: '3.1.0',
    date: '2026-06-25',
    changes: [
      'Groundwork for analytics: new DB table company_profiles (HQ, industry, company type, employee count, founding year, LinkedIn URL) for background company-data sync.',
      'Applications gain company_profile_id and target_company_profile_id (for headhunter applications) as foreign keys.',
    ],
  },
  {
    version: '3.0.4',
    date: '2026-06-25',
    changes: [
      'Fix: LI job description — a TreeWalker now finds the "About the job" section directly, no more class-name matching needed.',
    ],
  },
  {
    version: '3.0.3',
    date: '2026-06-25',
    changes: [
      'Fix: the description extractor now excludes elements with nav/header/footer child nodes — prevents page chrome from being returned as the description.',
    ],
  },
  {
    version: '3.0.2',
    date: '2026-06-25',
    changes: [
      'Fix: job description in job search — structure-based DOM detection instead of class name (LI hashes all CSS classes). Finds the richest content block outside of nav/header/footer.',
    ],
  },
  {
    version: '3.0.1',
    date: '2026-06-25',
    changes: [
      'Fix: render the job description as HTML — innerHTML instead of innerText, dangerouslySetInnerHTML with prose styling on the frontend.',
    ],
  },
  {
    version: '3.0.0',
    date: '2026-06-25',
    changes: [
      'New: job search — its own tab for searching job boards directly from JobTracker',
      'LinkedIn integration: search directly via the existing LI session, results with company, role, location, and easy-apply flag',
      'Open other job boards (StepStone, Indeed, Xing, Experteer, Headhunter24, Jobware) in the browser with one click — the search query is transferred automatically',
      'Select multiple results and add them as "prospecting" into JobTracker with one click — duplicates are detected and skipped',
      'Settings › job boards: add, edit, and enable/disable your own boards',
    ],
  },
  {
    version: '2.6.5',
    date: '2026-06-25',
    changes: [
      'Fix: the Kanban board now uses the full viewport width (outside max-w-7xl) — lanes no longer get cut off, horizontal scrolling works across the full screen width.',
      'Fix: generic department email addresses (career@, jobs@, recruiting@, bewerbung@, hr@, and others) are no longer created as contacts and no longer attached to multiple applications.',
    ],
  },
  {
    version: '2.6.3',
    date: '2026-06-25',
    changes: [
      'PDF export: landscape format (A4 sideways), wider columns, overflow protection with ellipsis',
      'PDF export: an overview of appointments from the last 4 weeks (interviews & calls) after the applications list',
      'Fix: LI sync wasn\'t backfilling stellenanzeige_url on existing applications — now filled in on the next sync if still empty.',
      'Fix: the LI sync action log showed no company/role — now correctly taken from the DB application.',
    ],
  },
  {
    version: '2.6.1',
    date: '2026-06-24',
    changes: [
      'Documents as their own section below the timeline — no longer as timeline events',
      'Clicking a file opens it directly in the associated Mac app (PDF → Preview, DOCX → Word, …)',
      'The file row shows the filename, extension, and a delete button (appears on hover)',
    ],
  },
  {
    version: '2.6.0',
    date: '2026-06-24',
    changes: [
      'Backup: automatic and manual database backup into a configurable Mac folder',
      'Settings › Backup: folder, frequency (hourly to weekly), number of backups to keep, "back up now" button, list of existing backups',
      'Scheduler: backup runs automatically in the background when enabled and due',
    ],
  },
  {
    version: '2.5.8',
    date: '2026-06-24',
    changes: [
      'Fix: last_sync was set after every sync run, even when 0 files had been created — this permanently skipped all files on the next sync via the since filter. last_sync is now only set when at least one file was newly created.',
    ],
  },
  {
    version: '2.5.7',
    date: '2026-06-24',
    changes: [
      'Fix: the DB migration reset main_status to its old value on every container restart if the legacy "status" column was still populated — affected e.g. Contoso AG #119 (manually set to "applied", reverted to "rejected" after every deploy). The old column is now dropped on first start; the migration only overwrites rows with a NULL status.',
    ],
  },
  {
    version: '2.5.6',
    date: '2026-06-24',
    changes: [
      'Auto-sync documents: folders are now also disambiguated by role — with multiple applications for the same company, the folder name is checked against the role title (example: "Contoso AG Senior Software Engineer"). Recursive: all files in arbitrarily deep subfolders are captured.',
    ],
  },
  {
    version: '2.5.5',
    date: '2026-06-24',
    changes: [
      'Auto-sync documents: folders one level below the configured root folder are treated directly as application folders — the folder name is matched against the company name, all files in it are attached as an event (type "file"), without per-file AI/keyword analysis',
    ],
  },
  {
    version: '2.5.4',
    date: '2026-06-24',
    changes: [
      'Manual document sync: the browser starts in the configured root folder but allows free navigation across the whole file system (path bar with click navigation, an "up" arrow, a "↩ home folder" key)',
      'Add an entire folder: a + button next to every folder attaches all files in it recursively to the application',
    ],
  },
  {
    version: '2.5.3',
    date: '2026-06-24',
    changes: [
      'Audit log: a SQLite trigger catches every main_status change at the DB level — even when the Python code path doesn\'t create an entry (the entry then appears with source="db_trigger")',
      'Modal: saving now only sends actually changed fields, preventing an unwanted status overwrite from stale modal state',
      'Merge: a status change via field_overrides is now explicitly logged as status_change',
    ],
  },
  {
    version: '2.5.2',
    date: '2026-06-24',
    changes: [
      'Document sync: auto-sync now matches files by the direct subfolder in the documents root folder (no longer by the immediate parent folder)',
      'Document sync: manual sync — a new "add document" button in every application\'s sync menu opens a file browser with folder navigation below the configured root folder',
      'Files bridge: new endpoints /browse (folder/file list without text extraction) and /file (a single file with text content)',
    ],
  },
  {
    version: '2.5.1',
    date: '2026-06-24',
    changes: [
      'LI sync: "No longer accepting applications" and "position no longer available" are now ignored — these messages refer to the job posting\'s status, not the applicant\'s own status in the tracker',
    ],
  },
  {
    version: '2.5.0',
    date: '2026-06-24',
    changes: [
      'Audit log: a complete change log for all applications — when, by whom (source), and why something was changed',
      'Records: status changes (manual + via PendingMatch), create, delete, merge, Excel import, LI-sync creation',
      'Log level selectable in Settings: off / normal (default) / verbose (+ all field changes)',
      'An audit-log button in the header (clipboard icon) opens a global view with filters by application and pagination',
    ],
  },
  {
    version: '2.4.7',
    date: '2026-06-24',
    changes: [
      'Fix: a normal sync created a new review suggestion for every new rejection email — a missing already_reviewed check (same as the LI-sync fix) in _save_deterministic_event, process_item (the AI path), and save_classified_event; rejection suggestions per app+target-status are no longer recreated after a one-time review decision',
    ],
  },
  {
    version: '2.4.6',
    date: '2026-06-24',
    changes: [
      'Fix: LI sync created new applications from the archived category directly as "rejected" — they\'re now created as "applied" with a review suggestion (also affects status_hint="rejected" on creation)',
    ],
  },
  {
    version: '2.4.5',
    date: '2026-06-24',
    changes: [
      'Syncs never automatically change application status anymore — all status suggestions (normal sync, targeted sync, LI sync) land in the manual review queue (PendingMatch); targeted sync now has this logic too (it was previously silently ignored)',
    ],
  },
  {
    version: '2.4.4',
    date: '2026-06-24',
    changes: [
      'Fix: targeted sync (the sync button in the modal) now respects merge aliases — emails using the old company name of merged applications are now found correctly',
    ],
  },
  {
    version: '2.4.3',
    date: '2026-06-24',
    changes: [
      'Fix: checkboxes in the table view couldn\'t select entries — both the TD onClick and the input onChange called onToggleSelect, immediately undoing the selection',
    ],
  },
  {
    version: '2.4.2',
    date: '2026-06-24',
    changes: [
      'Fix: an application was suggested as "rejected" again after every LI sync, even though the suggestion had already been rejected/approved — already-reviewed suggestions (approved/rejected) per app+target-status are no longer recreated (fixes Contoso AG #119)',
    ],
  },
  {
    version: '2.4.1',
    date: '2026-06-24',
    changes: [
      'Rejected applications: now appear, when shown, in the column of their last active status (no more separate "rejected" column) — marked in red (border, strikethrough, background) in both Kanban and table',
      'Merge feature: merge applications and contacts — select 2+ entries (table: checkboxes), the merge dialog shows fields side by side, choose per field which value to keep; events and contacts are merged automatically',
      'Merge alias: after merging, the old names are saved — future syncs (LI and normal) recognize the original company/role names and no longer create duplicates',
      'LinkedIn sync: progress display per stage — during scraping: page X — Y found per category; after each category: a results table with counts; during processing: a progress bar X/Y',
      'Fixed duplicate detection: company + role must be normalized-equal (not a substring) — GmbH/AG/SE etc. are ignored, gender markers (m/w/d) removed from the role; applies to LI sync and Excel import',
      'Ghosting for rejected applications: rejected applications with a >= 14-day gap between application and rejection are now also marked as ghosting; the "ghosting only" filter now also loads rejected ones',
      'Fix: the ghosting filter showed no entries — letztes_update was overwritten in-memory by a sync event (application submitted, date=today) before ghosting was serialized',
      'Job-posting URL: a new field on the application form — a link to the posting, manually editable; LinkedIn sync fills it in automatically',
      'Ghosting: now computed automatically (letztes_update > 14 days, no terminal status) — no more manual setting needed; a new cross-status "ghosting only" filter',
      'Rejected flag: now a computed property (main_status == rejected) — no more redundant checkbox, no sync overhead',
      'Sync fix: rejected applications excluded from the company index — prevents cross-matching with multiple applications at the same company (e.g. Contoso AG)',
      'LinkedIn sync: switched parsing to a company·location anchor — finds all entries regardless of whether a note is present (fixes missing interview entries)',
    ],
  },
  {
    version: '2.2.0',
    date: '2026-06-23',
    changes: [
      'LinkedIn sync: fully switched to text-based parsing (inner_text + an "add note" separator) — replaces fragile JS DOM scraping; reads company, role, location, applied date, and status hints directly from the page text',
      'LinkedIn sync: the dedup key is now company + role (instead of the LinkedIn job ID) — more robust against URL changes',
      'LinkedIn sync: simplified pagination — just clicking Next now, no more scrolling needed',
    ],
  },
  {
    version: '2.1.0',
    date: '2026-06-17',
    changes: [
      'Issue #1: removed the signature field from the PDF export',
      'Issue #2: calendar change detection — moved/deleted appointments are automatically updated/removed in the timeline during sync (iCloud Calendar + Google Calendar)',
      'Issue #3: manual assign — a new button in the sync dropdown opens a candidates panel with direct assignment, no AI; asks for confirmation on conflict if the entry is already in another application',
      'Issue #4: extended duplicate cleanup — contacts by name, cross-application events by external_id; both go into manual follow-up instead of automatic deletion',
      'Issue #5: file attachments — attachments are stored in the container, shown in the timeline, and can be downloaded; >100 MB goes into manual follow-up',
      'Issue #6: deep links in the timeline — Gmail, Google Calendar, iCloud Mail/Calendar/Notes can be opened directly in the respective app (clickable source badge)',
      'Issue #7: application date read-only — datum_bewerbung can now only be set via the timeline\'s "application" event; changes automatically sync the database field',
      'Internal: an external_id field on the event table for deep links and cross-app duplicate detection',
    ],
  },
  {
    version: '2.0.42',
    date: '2026-06-17',
    changes: [
      'Fix: all LinkedIn categories now use jobs-tracker/?stage= (saved/in-progress/applied/interview/archived) — full pagination for every tab, no more my-items URL',
    ],
  },
  {
    version: '2.0.41',
    date: '2026-06-17',
    changes: [
      'Fix: ARCHIVED pagination — a native Playwright click instead of JS evaluate + wait_for_load_state("networkidle") instead of polling; raised the stale_rounds threshold to 5',
      'Debug: the Excel export now includes a "pagination log" sheet with every click and stale event per category',
    ],
  },
  {
    version: '2.0.40',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn sync no longer creates duplicates — every application gets its LinkedIn job ID saved on the first sync; all following syncs match primarily on that (no more fuzzy string comparison needed)',
    ],
  },
  {
    version: '2.0.39',
    date: '2026-06-17',
    changes: [
      'New: LinkedIn sync no longer applies status changes directly — they land as a "status suggestion" in manual review (LinkedIn icon, text "LinkedIn reports a status change:")',
    ],
  },
  {
    version: '2.0.38',
    date: '2026-06-17',
    changes: [
      'Fix: interviews tab — context extraction limited to 500 characters per card, preventing every posting on a page from being taken as the context of a single posting (was causing the wrong company and fake duplicates)',
    ],
  },
  {
    version: '2.0.37',
    date: '2026-06-17',
    changes: [
      'Fix: the LinkedIn scraper now actively waits after clicking "Next" until new jobs appear in the DOM (max 12s) — prevents a premature stop on slow page transitions (this is why Archived had too few results)',
      'Fix: eliminated duplicates across categories — when the same posting appears in multiple tabs (e.g. Applied + Interviews), only the higher-priority category is kept',
    ],
  },
  {
    version: '2.0.36',
    date: '2026-06-17',
    changes: [
      'Fix: the interviews sync now uses the correct URL (linkedin.com/jobs-tracker/?stage=interview) instead of the invalid ?cardType=INTERVIEWS URL — LinkedIn ignored the parameter and wrongly showed the Saved tab',
    ],
  },
  {
    version: '2.0.35',
    date: '2026-06-17',
    changes: [
      'Debug: the LinkedIn scraper saves the raw HTML of every category to /tmp/linkedin_capture_CATEGORY.html after page load, for offline testing',
    ],
  },
  {
    version: '2.0.34',
    date: '2026-06-17',
    changes: [
      'Fix: "database is locked" during LinkedIn sync — raised busy_timeout to 60s; secured critical db.commit() calls with retry logic (up to 5 attempts)',
    ],
  },
  {
    version: '2.0.33',
    date: '2026-06-17',
    changes: [
      'Fix: the LinkedIn pagination Next button is now found via JavaScript (not a CSS selector) — works regardless of locale and LinkedIn version',
      'Fix: job extraction now also recognizes /jobs/collections/, /jobs/detail/, and data-job-id attributes — covers interview-tab links',
    ],
  },
  {
    version: '2.0.32',
    date: '2026-06-17',
    changes: [
      'Fix: the LinkedIn scraper only paginates page 1 for APPLIED/SAVED/IN_PROGRESS (current jobs), all pages for ARCHIVED and INTERVIEWS — prevents old archived jobs from showing up as "applied"',
      'Fix: LinkedIn INTERVIEWS — JS extraction now also recognizes /jobs/collections/ and other LI job URL types',
    ],
  },
  {
    version: '2.0.31',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn INTERVIEWS — JS extraction now also recognizes /jobs/collections/ and other LI job URL types (not just /jobs/view/); interview cards use different link formats',
    ],
  },
  {
    version: '2.0.30',
    date: '2026-06-17',
    changes: [
      'Fix: a SQLite TypeError when creating new LinkedIn applications — datum_bewerbung/letztes_update passed as a date object instead of a string',
    ],
  },
  {
    version: '2.0.29',
    date: '2026-06-17',
    changes: [
      'Fix: the LinkedIn scraper now waits for the first job link in the DOM (wait_for_selector) before running JS — LinkedIn renders interview cards asynchronously, so only 1 of 6 were being found',
    ],
  },
  {
    version: '2.0.28',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn ARCHIVED/INTERVIEWS use page-based pagination (1/2/3/Next), not infinite scroll — the scraper now clicks through the "Next" button before scrolling',
    ],
  },
  {
    version: '2.0.27',
    date: '2026-06-17',
    changes: [
      'Debug: after page load, the LinkedIn scraper logs all buttons, scrollable containers, and page height; after every scroll attempt, DOM height and job-link count — visible in the sync log',
    ],
  },
  {
    version: '2.0.26',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn scraper scroll — real mouse-wheel events (page.mouse.wheel) after scrollIntoView instead of the End key; reliably triggers LinkedIn\'s IntersectionObserver; raised the stale tolerance to 5 rounds (was 3)',
    ],
  },
  {
    version: '2.0.25',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn scraper — scroll now uses scrollIntoView on the last job card + the End key; works on the "My Jobs" page regardless of container layout',
    ],
  },
  {
    version: '2.0.24',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn scraper — company name showed ", Verified" when the badge text became empty after normalization (added an ln_norm filter)',
      'Fix: LinkedIn scraper — scroll now targets the internal list div instead of window (LinkedIn lazy-loads via the container\'s scrollTop)',
      'Fix: debug Excel — the raw-context column was empty (_raw_context was missing from the raw dict)',
    ],
  },
  {
    version: '2.0.23',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn scraper — set-based stale tracking (all_dom_ids) replaces dom_count; also works with virtual scrolling',
      'Fix: date extraction — the JS extractor without a \\n condition, an aria-label fallback, raw context as a last resort',
      'Debug: the raw-context column in the debug Excel shows what the scraper reads from the DOM',
    ],
  },
  {
    version: '2.0.22',
    date: '2026-06-17',
    changes: [
      'Fix: the LinkedIn scraper now scrolls through all pages — stale detection is based on the DOM element count instead of unique new jobs; scrollTo(scrollHeight) instead of scrollBy(800px); the "show more results" button gets clicked',
    ],
  },
  {
    version: '2.0.21',
    date: '2026-06-17',
    changes: [
      'Feature: a LinkedIn debug Excel after sync — every posting found with LI job ID, company, role, date, category, status hint, and DB action; a "categories" sheet shows match counts per LI category',
    ],
  },
  {
    version: '2.0.20',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn date detection for bare "m" (2m, 3m, 4m, 5m ago) — added to both the line filter and the parser (mo? covers m and mo)',
    ],
  },
  {
    version: '2.0.19',
    date: '2026-06-17',
    changes: [
      'Fix: application date in the table view — now automatically derived from the earliest "application" event when the DB field is empty (mostly affects LinkedIn entries)',
    ],
  },
  {
    version: '2.0.18',
    date: '2026-06-16',
    changes: [
      'Feature: PDF export "proof of independent job-search efforts" for the German Federal Employment Agency — applications from 2026-02-01 onward as a structured list with a header, footer, and signature field',
    ],
  },
  {
    version: '2.0.17',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn sync — archived entries were being overwritten by a seen_ids set shared with earlier categories; now isolated per category (ARCHIVED correctly beats APPLIED)',
    ],
  },
  {
    version: '2.0.16',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn scraper — fixed a company/role mix-up caused by the ", Verified" badge; added date parsing for the short format (6d/2w/1mo)',
    ],
  },
  {
    version: '2.0.15',
    date: '2026-06-16',
    changes: [
      'Fix: calendar appointments no longer suggest status changes in review — appointments are entries, not status communication',
    ],
  },
  {
    version: '2.0.14',
    date: '2026-06-16',
    changes: [
      'Feature: "next step" — a smart computed field in the table and Kanban (upcoming appointments, feedback status, ghosting warning, stage-based recommendation)',
    ],
  },
  {
    version: '2.0.13',
    date: '2026-06-16',
    changes: [
      'Fix: "last update" now ignores future appointments — shows the last actual activity, not the next scheduled appointment',
    ],
  },
  {
    version: '2.0.12',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Archived → Rejected now applies to all stages (not just the early phase) — regardless of the previous status',
    ],
  },
  {
    version: '2.0.11',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn scraper — a new JS-based approach for LinkedIn job extraction (layout-stable, cookie consent gets automatically dismissed)',
    ],
  },
  {
    version: '2.0.10',
    date: '2026-06-16',
    changes: [
      'Feature: LinkedIn 2FA inline — enter an app push notification or a code from email/SMS directly in the app',
    ],
  },
  {
    version: '2.0.9',
    date: '2026-06-16',
    changes: [
      'UX: switched Settings to a sidebar layout — scales cleanly with many tabs',
      'Feature: a LinkedIn tab in Settings — configuration and sync right there',
    ],
  },
  {
    version: '2.0.8',
    date: '2026-06-16',
    changes: [
      'Feature: LinkedIn sync shows a detailed action log after completion (new / rejected / updated)',
      'Fix: LinkedIn archive entries are now correctly marked as rejected (abgesagt=true, status=rejected) when the application is still in an early phase (applied/prospecting)',
    ],
  },
  {
    version: '2.0.7',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn login — replaced networkidle with domcontentloaded (LinkedIn never reaches networkidle because of background requests)',
    ],
  },
  {
    version: '2.0.6',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn login — wait for networkidle instead of domcontentloaded, then explicitly for #username with a 10s timeout',
    ],
  },
  {
    version: '2.0.5',
    date: '2026-06-16',
    changes: [
      'Perf: moved Playwright Chromium into a separate Docker base image — only rebuilt when the Playwright version or Dockerfile.playwright-base changes',
      'Perf: normal deploys now skip the Chromium download entirely (~10 min saved)',
    ],
  },
  {
    version: '2.0.4',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn login timeout — now explicitly waits for React form hydration before filling in fields',
    ],
  },
  {
    version: '2.0.3',
    date: '2026-06-16',
    changes: [
      'Perf: sync sources now load already-indexed IDs into a set once instead of running a DB query per item',
      'Perf: progress updates only every 10 items instead of every step (fewer DB writes)',
      'Perf: the is_synced check in gcal/iCloud calendar now runs before the keyword filter',
    ],
  },
  {
    version: '2.0.2',
    date: '2026-06-16',
    changes: [
      'Fix: the local-documents toggle state is now saved and loaded correctly',
    ],
  },
  {
    version: '2.0.1',
    date: '2026-06-16',
    changes: [
      'Fix: the "documents" tab in Settings was cut off — the tab bar is now horizontally scrollable',
    ],
  },
  {
    version: '2.0.0',
    date: '2026-06-16',
    changes: [
      'New sync system: deterministic classification replaces AI for ~90% of cases (calendar, local files, single-company matching)',
      'Background sync: automatic indexing every 20 minutes via an asyncio loop',
      'New source: local application documents (PDF, DOCX, TXT, MD) via files_bridge.py on port 9998',
      'Settings → "documents" tab: configure the folder path, bridge status, manual sync',
      'Sync control: a new "local documents" toggle in the sync control panel',
      'An empty company match now immediately skips AI instead of making an unnecessary API call',
    ],
  },
  {
    version: '1.0.8',
    date: '2026-06-14',
    changes: [
      'Fix: short forms of company names with 4–5 characters (e.g. "Opitz") are now captured in the search index',
    ],
  },
  {
    version: '1.0.7',
    date: '2026-06-14',
    changes: [
      'Sync control: Google / Apple / LinkedIn can be toggled on/off as a whole and per individual source',
      'A new "sync control" tab in Settings with master toggles and sub-sources',
      'SyncButton now skips disabled sources during a global sync',
    ],
  },
  {
    version: '1.0.6',
    date: '2026-06-14',
    changes: [
      'Apple Notes sync: a pre-filter skips notes with no company-name match (no AI call)',
      'Apple Notes sync: parallel AI calls in batches of 5 instead of sequentially',
    ],
  },
  {
    version: '1.0.5',
    date: '2026-06-13',
    changes: [
      'Your own contact is now skipped during sync (Google, iCloud, and LinkedIn accounts)',
      'The Google email is saved after OAuth (userinfo API) and recognized as the owner address',
      'googlemail.com ↔ gmail.com are now treated as the same address',
    ],
  },
  {
    version: '1.0.4',
    date: '2026-06-13',
    changes: [
      'Kanban: order within a column is now by last update (newest → oldest)',
    ],
  },
  {
    version: '1.0.3',
    date: '2026-06-13',
    changes: [
      'Calendar week view: fixed column height, each day column scrolls independently',
    ],
  },
  {
    version: '1.0.2',
    date: '2026-06-13',
    changes: [
      'The calendar now shows only real appointments (interview, gcal, iCloud Cal) – no mails, notes, or status changes',
    ],
  },
  {
    version: '1.0.1',
    date: '2026-06-13',
    changes: [
      'Fix: sync progress showed another application\'s data (e.g. Contoso GmbH instead of Fabrikam GmbH)',
    ],
  },
  {
    version: '1.0.0',
    date: '2026-06-13',
    changes: [
      'Calendar view: day / work week / week / month (Outlook style)',
      'Events color-coded by application status',
      'Clicking an appointment opens a detail modal with a link to the application',
      'Backend: GET /api/calendar/events with a date filter',
      'Auto-deploy via GitHub Actions + a self-hosted runner (SSH auth)',
    ],
  },
  {
    version: '0.9.0',
    date: '2026-06-13',
    changes: [
      'GitHub repo + CI/CD pipeline (ruff, tsc, Docker Buildx)',
      'Technical architecture documentation (docs/ARCHITECTURE.md)',
      'Updated the project-status doc and moved it into the docs/ directory',
      'Fixed all ruff lint errors (E402, E702, E712, F401, F811, F821)',
    ],
  },
  {
    version: '0.8.0',
    date: '2026-06-13',
    changes: [
      'Version number + changelog modal in the header',
      'A lifecycle bar in the application detail view (horizontal progress)',
      'Last update computed dynamically from max(timeline event)',
      'Time of day for mail events in the timeline (HH:MM)',
      'ID as its own column in the table and on Kanban cards',
      'Last update shown at the bottom of Kanban cards',
    ],
  },
  {
    version: '0.7.0',
    date: '2026-06-12',
    changes: [
      'Contacts overview: company as its own column, sorting by name/company/type/last contact',
      'Contact upsert from mail/calendar sync (name, email, phone, role from the footer)',
      'Targeted sync: sync all sources in parallel for a single application',
      'A LinkedIn Playwright scraper with cached session cookies',
      'Call history via calls_bridge.py (macOS CallHistoryDB)',
      'iCloud Notes via notes_bridge.py (AppleScript/JXA)',
    ],
  },
  {
    version: '0.6.0',
    date: '2026-06-11',
    changes: [
      'Google OAuth 2.0 + Gmail + Google Calendar sync',
      'iCloud Mail (IMAP), Calendar (CalDAV), Contacts (CardDAV)',
      'AI classification via LiteLLM (Groq, Ollama, OpenAI-compatible)',
      'A review queue for AI suggestions with manual approval',
      'Fernet encryption for all credentials and API keys',
      'Dedup via a synced_items table (source + external_id)',
    ],
  },
  {
    version: '0.5.0',
    date: '2026-06-10',
    changes: [
      'Excel export in the original format (17 columns, sheet "Tracking")',
      'Contact management (CRM): a many-to-many link with applications',
      'Duplicate cleanup for applications, contacts, and events',
      'A status popover: change status directly in the table row',
      'An AI settings modal: provider, model, API key, connection test',
    ],
  },
  {
    version: '0.4.0',
    date: '2026-06-09',
    changes: [
      'A two-tier status model: main_status + sub_status',
      'Migrated the old flat status (hr_scheduled → hr + 1_scheduled)',
      'A sub-status sequence for the HR and FB stages (1_scheduled → 1_done → …)',
      'An automatic status event on every status change',
      'KPI tiles in StatsBar',
    ],
  },
  {
    version: '0.3.0',
    date: '2026-06-08',
    changes: [
      'A Kanban board by main_status column',
      'A detail/edit modal with a timeline and interview notes',
      'Colored status badges',
    ],
  },
  {
    version: '0.2.0',
    date: '2026-06-07',
    changes: [
      'Excel import (Bewerbungen_Eugen_Gulinsky.xlsx, 133 entries)',
      'A sortable table view',
      'Search filters (company, role, source)',
    ],
  },
  {
    version: '0.1.0',
    date: '2026-06-06',
    changes: [
      'A FastAPI backend + SQLite (WAL)',
      'CRUD endpoints for applications and events',
      'A React 18 + TypeScript + Tailwind CSS frontend',
      'Docker Compose, OrbStack-compatible',
    ],
  },
]

export const CURRENT_VERSION = CHANGELOG[0].version

interface Props {
  open: boolean
  onClose: () => void
}

export function ChangelogModal({ open, onClose }: Props) {
  const { t } = useTranslation('common')
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <span className="font-semibold text-gray-900">Changelog</span>
            <span className="ml-2 text-xs text-gray-400">rapport</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-5">
          {CHANGELOG.map((r, i) => (
            <div key={r.version}>
              <div className="flex items-center gap-3 mb-2">
                <span className={`font-mono font-bold text-sm ${i === 0 ? 'text-indigo-600' : 'text-gray-700'}`}>
                  v{r.version}
                </span>
                {i === 0 && (
                  <>
                    <span className="text-[10px] font-semibold bg-indigo-100 text-indigo-600 rounded px-1.5 py-0.5">
                      {t('current')}
                    </span>
                    <span className="text-[10px] text-gray-400 font-mono">
                      Build {BUILD_NUMBER}
                    </span>
                  </>
                )}
                <span className="text-xs text-gray-400 ml-auto">{r.date}</span>
              </div>
              <ul className="space-y-1">
                {r.changes.map((c, j) => (
                  <li key={j} className="flex gap-2 text-sm text-gray-600">
                    <span className="text-gray-300 mt-0.5 flex-shrink-0">–</span>
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
              {i < CHANGELOG.length - 1 && <div className="mt-4 border-t border-gray-100" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
