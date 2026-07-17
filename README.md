<p align="center">
  <img src="frontend/public/brand/logo.svg" alt="rapport" width="220" />
</p>

# rapport

Self-hosted CRM for your job search — a replacement for the Excel application list.
Runs locally in OrbStack / Docker Compose. Current status: see the in-app changelog (version in `frontend/src/components/ChangelogModal.tsx`).

Technical architecture with diagrams: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Download (recommended for non-developers)

Prebuilt installers for macOS, Windows, and Linux are attached to each
[GitHub Release](https://github.com/EGulinsky/rapport/releases) — download
`Rapport-Installer-<version>.{dmg,zip,tar.gz}` for your OS and run it once.
It installs Docker automatically if it's missing, pulls the prebuilt app
images, starts them, and opens the app in your browser — no manual Docker
setup or terminal commands needed. See [installer/README.md](installer/README.md)
for details on what it does under the hood.

The same releases also include `Rapport-Agent-<version>.{dmg,zip,tar.gz}` —
the separate native helper for local file/notes/calls access, see
[agent/README.md](agent/README.md).

## Requirements (developer setup)

- [OrbStack](https://orbstack.dev/) or Docker Desktop (Mac / Linux / Windows)

## Quick Start

```bash
# 1. Change into the project folder
cd /Users/eugengulinsky/code/rapport

# 2. Start the app (first build takes ~2–3 minutes)
docker compose up -d --build

# 3. Open the browser
open http://localhost:3000
```

## Features

| Feature | Description |
|---|---|
| **Dashboard / Table** | All applications, sortable; "next step" intelligently computed |
| **Kanban board** | Pipeline view with drag & drop across status columns |
| **Calendar view** | Outlook-like: day / work week / week / month |
| **Filter & search** | By status, free text, show/hide rejected |
| **Detail modal** | Full profile, lifecycle bar, timeline, interview notes |
| **Salary tracking** | Your expectation vs. the company's budget, single value or min–max range, optional fixed+bonus breakdown, company-car flag, selectable currency; flags a mismatch when the budget can't meet your expectation |
| **Contacts (CRM)** | Contact persons with n:m linking to applications |
| **Excel import** | `.xlsx` in the original format (sheet "Tracking", 17 columns) |
| **Excel export** | Re-export to the same format |
| **KPI tiles** | Total / active / rejected / interview rate |
| **LinkedIn sync** | Playwright scraper: reconcile your own application activity, status updates incl. rejections |
| **Gmail sync** | Google OAuth 2.0, link application-relevant emails |
| **Google Calendar** | Interview appointments as events, contacts from the attendee list |
| **iCloud Mail** | IMAP sync (app-specific password) |
| **iCloud Calendar** | CalDAV sync |
| **iCloud Contacts** | CardDAV import + manual full-text search of the address book |
| **LinkedIn contact import** | People search directly in the contacts overview, import a selection |
| **Location autocomplete** | Google Places (with API key) or Nominatim fallback |
| **Local documents** | PDF/DOCX/TXT/MD via the Rapport Agent |
| **Review queue** | Approve AI suggestions for events and status changes |
| **Sync control** | Enable/disable sources individually |
| **AI classification** | Provider-agnostic via LiteLLM (Groq, Ollama, OpenAI, Anthropic) |
| **AI success assessment** | Traffic light (green/yellow/red) per application incl. reasoning + next step; rejection-reason analysis for rejections |
| **LinkedIn import** | Paste a job-posting link → company/role/source automatically extracted via AI |
| **Company profiles** | Dedicated company view with logo, industry, location, employee count (automatically enriched) |
| **Merge** | Manually or automatically merge duplicates among applications, contacts, and companies |
| **Cleanup** | Context-sensitive duplicate detection (applications/contacts/companies/calendar) |
| **File attachments** | Attachments from sync sources on timeline events, downloadable |
| **PDF export** | Export your own job-search activity as a PDF |
| **Analytics** | Pipeline funnel and rejection statistics |
| **Audit log** | Traceable change history per application |
| **Backup** | Configurable local database backups |
| **Changelog** | Version history available in the app header |
| **Multi-account** | Self-registration with email confirmation; each account sees only its own data |
| **Language** | English/German UI, selectable at registration and in Settings — applies to the frontend, backend error messages, emails, AI assessment reasoning, and the native macOS agent's menu bar |

## Settings

### LinkedIn
1. Settings → LinkedIn → enter email + password
2. "Start sync" — for 2FA: confirm the push notification **or** enter the code

### Google (Gmail + Calendar)
1. Google Cloud Console → OAuth 2.0 client (web), redirect URI: `http://localhost:8000/api/sync/google/callback`
2. Settings → Google: enter client ID + secret → start the OAuth flow

### iCloud (Mail + Calendar + Contacts)
1. Apple ID → Security → App-Specific Passwords → generate a new password
2. Settings → iCloud: enter Apple ID + app password

### Local Documents (+ Notes, Calls, Backup)
Requires the Rapport Agent on the Mac (see [agent/README.md](agent/README.md) — installable as a `.app`/`.dmg`, runs permanently in the background with a menu-bar icon, no more manual terminal windows). After installation: Settings → Agent → paste the token (shown in the menu bar the first time the agent starts). Then Settings → Documents → set the folder path.

### AI Provider
- **Groq** (recommended, free): API key from [console.groq.com](https://console.groq.com), model `groq/llama-3.3-70b-versatile`
- **Ollama** (local, no API key): base URL `http://host.docker.internal:11434`

### Location Autocomplete (Optional)
Without configuration, the "location" search automatically uses Nominatim (free, no POIs). For company locations/POIs: Settings → Maps → enter a Google Places API key.

## API Documentation

Swagger UI: `http://localhost:8000/docs`

## Isolated Test Environment

For safe testing (e.g. restoring from a production backup), there is a separate 1:1 environment with its own, empty database — completely isolated from the real data and clearly marked in the frontend with a red "TEST ENVIRONMENT" banner.

```bash
docker compose -p rapport-test -f docker-compose.test.yml up -d --build
```

- GUI: `http://localhost:3001`
- API/Swagger: `http://localhost:8001/docs`

Reset (also deletes the test database):

```bash
docker compose -p rapport-test -f docker-compose.test.yml down -v
```

## Stopping the App

```bash
docker compose down
```

Data is preserved (Docker volume `jobtracker-data`).

## Tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest -m "unit or component or api"    # 1250 tests, same gate as in CI
```

Details on the test concept: [docs/TEST_KONZEPT.md](docs/TEST_KONZEPT.md)

## Development Mode (Without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload    # http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

## License

[Business Source License 1.1](LICENSE) — free to use for private, non-commercial purposes. A separate license is required for commercial use.
