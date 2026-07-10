# JobTracker – Project Status

> **Historical snapshot from June 16, 2026 (v2.0.17).** For the continuously maintained, current technical state see [ARCHITECTURE.md](ARCHITECTURE.md) — routers, data model, and diagrams are always kept up to date there. This document is preserved as a snapshot of the early development phase.

**As of:** June 16, 2026 · **Version:** v2.0.17
**Project folder:** `/Users/eugengulinsky/code/jobtracker/`
**GitHub:** https://github.com/EGulinsky/jobtracker (private)
**Excel source file:** `Stellen/Bewerbungen_Eugen_Gulinsky.xlsx` (133 entries, backup exists)

---

## What Is JobTracker?

Self-hosted web application as a replacement for the Excel application list. Runs locally in OrbStack (Docker Compose). Goal: track application processes, manage contacts, sync Gmail/calendar/iCloud/LinkedIn, AI-assisted analysis.

**Local URL:** `http://192.168.117.10` (OrbStack) or `http://localhost:3000`
**API / Swagger:** `http://localhost:8000/docs`

---

## Current Development Status

### Backend (Python 3.11 / FastAPI + SQLite)

#### Routers (all under `/api/...`)

| File | Prefix | Function |
|---|---|---|
| `applications.py` | `/api/applications` | CRUD applications, events, contact linking; `naechster_schritt` (next step) computed |
| `contacts.py` | `/api/contacts` | Global contact management (n:m with applications) |
| `import_excel.py` | `/api/import/excel` | Multipart upload of the xlsx, status mapping |
| `export_excel.py` | `/api/export/excel` | Re-export as xlsx |
| `settings.py` | `/api/settings` | AI provider configuration (encrypted) |
| `calendar.py` | `/api/calendar` | Calendar events by date (all event types) |
| `sync_google.py` | `/api/sync/google` | Google OAuth 2.0 + Gmail + Calendar sync |
| `sync_icloud.py` | `/api/sync/icloud` | iCloud Mail (IMAP), Calendar (CalDAV), Contacts (CardDAV) |
| `sync_targeted.py` | `/api/sync/targeted` | Per-application sync across all sources simultaneously |
| `sync_files.py` | `/api/sync/files` | Local documents via files_bridge (port 9998) |
| `sync_linkedin.py` | `/api/sync/linkedin` | LinkedIn Playwright scraper with inline 2FA support |
| `sync_common.py` | – | Shared helpers: AI classification, contact upsert, dedup |
| `review.py` | `/api/review` | Review queue for AI suggestions; cleanup endpoint for calendar status |
| `cleanup.py` | `/api/cleanup` | Duplicate cleanup and data maintenance |

#### Database Models (SQLite, auto-created on startup)

| Model | Description |
|---|---|
| `Application` | Application with `main_status` + `sub_status` |
| `Contact` | Contact person, n:m with applications via join table |
| `Event` | Interaction (email, call, note, calendar), with a `source` field |
| `GoogleSync` | Google OAuth credentials (Fernet-encrypted) |
| `ICloudSync` | iCloud app password (Fernet-encrypted), IMAP/CalDAV |
| `PendingMatch` | AI-suggested matches, awaiting user approval |
| `SyncedItem` | Dedup table for already-processed external IDs |
| `AiSettings` | AI provider configuration (LiteLLM, Groq, Ollama, etc.) |
| `LinkedInSync` | LinkedIn credentials + cached session cookies |
| `FilesConfig` | Local documents: folder path + enabled |
| `CallsConfig` | Configuration for call-list sync |

#### AI Layer (`app/ai/`)
- **`provider.py`**: vendor-agnostic via **LiteLLM** — Groq, Ollama, OpenAI-compatible. API keys Fernet-encrypted.
- **`tasks.py`**: `classify_batch_for_app()` — classifies events in batches

#### LinkedIn Scraper (`sync_linkedin.py`)
- Headless Chromium via Playwright (separate `Dockerfile.playwright-base` — only rebuilt on a Playwright update)
- Scrapes 5 categories: SAVED / IN_PROGRESS / APPLIED / INTERVIEWS / ARCHIVED
- JS-based job extraction (robust against CSS changes)
- **2FA**: push notification auto-detected (URL polling) or manual code via `/submit-2fa`
- **Archived → rejected**: always, regardless of the previous status
- **Bug (fixed in v2.0.17):** `seen_ids` was shared globally → ARCHIVED was overwritten by the APPLIED pass. Now per-category.

#### JobTracker Agent (`agent/`, runs on the Mac, not in Docker)

A single background service (port 9996, bearer-token auth) replaces the
former three separate bridge scripts (`files_bridge.py`, `calls_bridge.py`,
`notes_bridge.py` — removed in v3.27.0). Installable as a `.app`/`.dmg`
(`agent/packaging/`), menu-bar icon, registers itself on first launch
as a `launchd` LaunchAgent (autostart + restart on crash).
OS-adapter boundary (`agent/providers/`) for a planned Windows port.
Details: [agent/README.md](../agent/README.md).

| Module | Function |
|---|---|
| Files | Local application documents (PDF, DOCX, TXT, MD), backup file access |
| Calls | iPhone call list (CallHistoryDB) + WhatsApp calls |
| Notes | iCloud Notes via AppleScript (JXA) |

---

### Frontend (React 18 + Vite + TypeScript + Tailwind)

#### Components

| File | Function |
|---|---|
| `App.tsx` | Main component: dashboard, filters, view switching |
| `ApplicationTable.tsx` | Sortable table with a "next step" column (color-coded) |
| `KanbanBoard.tsx` | Drag & drop Kanban by `main_status` columns (dnd-kit) |
| `ApplicationModal.tsx` | Detail/edit modal: status, lifecycle bar, contacts, timeline |
| `CalendarView.tsx` | Outlook-like calendar view: day / work week / week / month |
| `StatusBadge.tsx` | Colored badges for main_status + sub_status |
| `StatusPopover.tsx` | Inline dropdown for status change directly in the table |
| `ContactsView.tsx` | CRM contact list linked to applications |
| `StatsBar.tsx` | KPI tiles: total / active / rejected / interview rate |
| `ImportButton.tsx` | Excel upload |
| `ExportButton.tsx` | Excel download |
| `SyncButton.tsx` | Global sync trigger with sync control (toggle sources on/off) |
| `LinkedInSyncButton.tsx` | LinkedIn sync with inline 2FA dialog (amber box for code entry) |
| `ReviewModal.tsx` | Review inbox: approve or reject AI suggestions |
| `SettingsModal.tsx` | Settings (sidebar layout): Google / iCloud / LinkedIn / documents |
| `AiSettingsModal.tsx` | Choose AI provider (Groq/Ollama/OpenAI), API key, test |
| `ChangelogModal.tsx` | Version history; `CURRENT_VERSION` maintained here |
| `CleanupModal.tsx` | Clean up duplicates |

---

## Status Model (Two-Tier)

**Old (MVP):** flat enum (`applied`, `hr_scheduled`, `hr_done`, ...)
**Current:** `main_status` + optional `sub_status`

```
main_status:  prospecting | applied | hr | fb | waiting | negotiating | signed | rejected
sub_status:   1_scheduled | 1_done | 2_scheduled | 2_done | 3_scheduled | 3_done | ...
              (only for hr and fb)
```

Example: `hr + 2_done` = "HR interview, 2nd round completed"

Excel import map: `EXCEL_IMPORT_MAP` in `models.py`
Excel export map: `EXCEL_EXPORT_MAP` in `models.py`

---

## Deployment

```bash
# Start (OrbStack must be running)
cd /Users/eugengulinsky/code/jobtracker
docker compose up -d

# Rebuild after code changes (CI/CD does this automatically)
docker compose up -d --build

# JobTracker Agent (separate, on the Mac) — installed as a .app, runs permanently
# in the background (menu bar), no manual start needed. See agent/README.md.
```

**Docker services:**
- `backend` – FastAPI on port 8000, volume `jobtracker-data` for SQLite + Fernet key
- `frontend` – Nginx with the React build on port 3000, proxies `/api/*` → backend

**CI/CD:** GitHub Actions self-hosted runner (on the Mac)
- `backend` → ruff lint + pyright
- `frontend` → tsc + vite build
- `docker` → Docker Buildx, deploy via `docker compose up -d`

---

## Implemented (Current State)

- [x] FastAPI backend with SQLite (WAL)
- [x] All CRUD endpoints for applications + events + contacts
- [x] Excel import (133 entries, status mapping)
- [x] Excel export (original format, 17 columns)
- [x] React frontend (table, Kanban, calendar, contacts)
- [x] Two-tier status model (main_status + sub_status)
- [x] Lifecycle bar in the detail modal
- [x] KPI tiles (StatsBar)
- [x] Drag & drop Kanban (dnd-kit)
- [x] Calendar view (Outlook style: day/week/month)
- [x] "Next step" – intelligently computed field
- [x] Google OAuth 2.0 + Gmail + Google Calendar sync
- [x] iCloud Mail (IMAP) + calendar (CalDAV) + contacts (CardDAV) sync
- [x] LinkedIn Playwright scraper (session-cached, archived→rejected, inline 2FA)
- [x] Local documents/notes/calls sync via the JobTracker Agent (agent/)
- [x] AI classification via LiteLLM (Groq, Ollama, OpenAI-compatible)
- [x] Review queue for AI suggestions
- [x] Sync control: sources can be toggled on/off
- [x] Per-application targeted sync
- [x] Contact CRM (n:m with applications, contact upsert from sync)
- [x] Fernet encryption for all credentials
- [x] Background sync loop (every 20 minutes, asyncio)
- [x] CI/CD (GitHub Actions, self-hosted runner)
- [x] Version history (ChangelogModal, CURRENT_VERSION)
- [x] Duplicate cleanup

---

## What's Still Missing / Next Steps

- [ ] **Analytics page**: KPI charts, funnel, source effectiveness (Recharts)
- [ ] **Alembic migrations**: currently `create_all()` on startup; needed at the next schema-breaking change
- [ ] **Auth**: no login for MVP (single-user local)
- [ ] **Restrict CORS**: currently `allow_origins=["*"]`
- [ ] **JobTracker Agent Windows port**: architecture is designed to be cross-platform (provider interfaces in `agent/providers/`), Windows adapter not yet implemented

---

## File Structure

```
/Users/eugengulinsky/code/jobtracker/
├── CLAUDE.md                          ← Claude Code context (auto-read)
├── README.md                          ← Quick start
├── docker-compose.yml
├── agent/                              ← JobTracker Agent (Mac background service, replaces the old bridges)
├── .github/workflows/ci.yml           ← GitHub Actions CI/CD (self-hosted runner)
├── docs/
│   ├── ARCHITECTURE.md               ← Technical architecture (current)
│   ├── JobTracker_Projektstand.md    ← this document
│   └── JobTracker_Konzept_Architektur.md  ← original planning document
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.playwright-base    ← Separate Chromium base image
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── models.py                  ← All ORM models + status maps
│       ├── schemas.py
│       ├── database.py
│       ├── ai/
│       │   ├── provider.py            ← LiteLLM wrapper (Fernet crypto)
│       │   └── tasks.py
│       └── routers/
│           ├── applications.py
│           ├── contacts.py
│           ├── import_excel.py
│           ├── export_excel.py
│           ├── settings.py
│           ├── calendar.py
│           ├── sync_google.py
│           ├── sync_icloud.py
│           ├── sync_targeted.py
│           ├── sync_files.py
│           ├── sync_linkedin.py
│           ├── sync_common.py
│           ├── review.py
│           └── cleanup.py
└── frontend/
    └── src/
        ├── App.tsx
        ├── types.ts
        ├── api/client.ts
        └── components/
            ├── ApplicationTable.tsx
            ├── ApplicationModal.tsx
            ├── KanbanBoard.tsx
            ├── CalendarView.tsx
            ├── ContactsView.tsx
            ├── ReviewModal.tsx
            ├── SettingsModal.tsx
            ├── AiSettingsModal.tsx
            ├── SyncButton.tsx
            ├── LinkedInSyncButton.tsx
            ├── StatusBadge.tsx
            ├── StatusPopover.tsx
            ├── StatsBar.tsx
            ├── ImportButton.tsx
            ├── ExportButton.tsx
            ├── ChangelogModal.tsx
            └── CleanupModal.tsx
```
