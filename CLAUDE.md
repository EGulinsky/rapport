# JobTracker – Claude Code Kontext

Self-hosted Bewerbungs-Tracking-App (Ersatz für `Bewerbungen_Eugen_Gulinsky.xlsx`).  
Läuft lokal in OrbStack (Docker Compose). Aktueller Stand: v2.0.17.

## Projekt starten

```bash
# App starten (OrbStack / Docker muss laufen)
cd /Users/eugengulinsky/code/jobtracker
docker compose up -d

# Nach Code-Änderungen neu bauen
docker compose up -d --build

# Logs
docker compose logs -f backend
docker compose logs -f frontend
```

**URLs:**
- App: `http://192.168.117.10` (OrbStack static IP — kein nginx-Cache-Problem)
- API/Swagger: `http://localhost:8000/docs`
- Alternativ: `http://localhost:3000`

## Projektstruktur

```
jobtracker/
├── CLAUDE.md
├── README.md
├── docker-compose.yml
├── .github/workflows/ci.yml     # ruff + tsc + docker buildx, self-hosted runner
├── docs/
│   ├── ARCHITECTURE.md          # Technische Architektur (aktuell)
│   ├── JobTracker_Projektstand.md
│   └── JobTracker_Konzept_Architektur.md   # Ursprüngliches Planungsdokument
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.playwright-base   # Separates Base-Image mit Chromium (~10 min Build)
│   ├── requirements.txt
│   └── app/
│       ├── main.py          # FastAPI App + CORS + Lifespan + Background-Sync-Loop
│       ├── database.py      # SQLAlchemy Engine + SessionLocal
│       ├── models.py        # ORM-Modelle + Status-Enums + Excel-Maps
│       ├── schemas.py       # Pydantic Request/Response-Schemas
│       ├── ai/
│       │   ├── provider.py  # litellm-Wrapper + Fernet-Kryptographie
│       │   └── tasks.py     # classify_batch_for_app()
│       └── routers/
│           ├── applications.py   # CRUD + Events + Contacts; naechster_schritt berechnet
│           ├── contacts.py       # Globale Kontaktverwaltung
│           ├── import_excel.py   # POST /api/import/excel
│           ├── export_excel.py   # GET /api/export/excel
│           ├── settings.py       # AI-Settings + Sync-Konfiguration
│           ├── calendar.py       # GET /api/calendar/events
│           ├── sync_common.py    # Dedup, AI-Klassifikation, Kontakt-Upsert
│           ├── sync_google.py    # Google OAuth + Gmail + GCal
│           ├── sync_icloud.py    # iCloud IMAP + CalDAV + CardDAV
│           ├── sync_targeted.py  # Pro-App-Sync für alle Quellen
│           ├── sync_files.py     # Lokale Dokumente (PDF/DOCX via files_bridge)
│           ├── sync_linkedin.py  # LinkedIn Playwright-Scraper
│           ├── review.py         # Review-Queue (PendingMatches)
│           └── cleanup.py        # Datenbereinigung
└── frontend/
    ├── Dockerfile
    └── src/
        ├── App.tsx              # Root: Filter, Tabs, Views
        ├── types.ts             # TypeScript-Typen, Status-Labels/Farben
        ├── api/client.ts        # Fetch-Wrapper für alle Backend-Calls
        └── components/
            ├── ApplicationTable.tsx    # Tabelle mit "Nächster Schritt"-Spalte
            ├── KanbanBoard.tsx         # Drag & Drop Kanban
            ├── ApplicationModal.tsx    # Detail/Edit mit Lifecycle-Bar + Timeline
            ├── CalendarView.tsx        # Outlook-ähnliche Kalenderansicht
            ├── StatsBar.tsx            # KPI-Kacheln
            ├── StatusBadge.tsx         # Farbige Status-Badges
            ├── StatusPopover.tsx       # Inline-Statuswechsel in Tabelle
            ├── ContactsView.tsx        # CRM-Kontaktübersicht
            ├── ReviewModal.tsx         # Review-Inbox für KI-Vorschläge
            ├── SettingsModal.tsx       # Einstellungen: Google/iCloud/LinkedIn/Dokumente
            ├── AiSettingsModal.tsx     # AI-Provider-Konfiguration
            ├── SyncButton.tsx          # Globaler Sync-Trigger
            ├── LinkedInSyncButton.tsx  # LinkedIn-Sync mit 2FA-Inline-Dialog
            ├── ImportButton.tsx        # Excel-Upload
            ├── ExportButton.tsx        # Excel-Download
            ├── ChangelogModal.tsx      # Versionsverlauf; CURRENT_VERSION hier pflegen
            └── CleanupModal.tsx        # Dubletten bereinigen
```

## Datenbank

SQLite unter `/app/data/jobtracker.db` (Docker Volume `jobtracker-data`).  
Schema via SQLAlchemy `create_all()` beim Start — kein Alembic.

## Status-Modell

Zweistufig: `main_status` + optionaler `sub_status`.

```
main_status: prospecting | applied | hr | fb | waiting | negotiating | signed | rejected
sub_status:  1_scheduled | 1_done | 2_scheduled | 2_done | 3_scheduled | 3_done | 4_scheduled | 4_done | 5_scheduled | 5_done
             (nur bei hr und fb relevant)
```

Pipeline (für `STATUS_ORDER` im Sync):
```
prospecting → applied → hr → fb → waiting → negotiating → signed
                                                                └→ (alle) → rejected
```

## Kryptographie

Alle sensitiven Felder (Passwörter, OAuth-Tokens, API-Keys) Fernet-verschlüsselt.  
Schlüssel: `backend/data/fernet.key` (im Docker Volume, nie committen).  
Funktionen: `encrypt_api_key()` / `decrypt_api_key()` in `app/ai/provider.py`.

## LinkedIn-Scraper

Headless Playwright (Chromium) im Backend-Container.  
Separates Base-Image `Dockerfile.playwright-base` — wird nur bei Playwright-Versions-Update neu gebaut.

**Kategorien** (Reihenfolge beachten!):
```python
CATEGORIES = [
    ("SAVED", "Gespeichert", "prospecting"),
    ("IN_PROGRESS", "In Bearbeitung", "applied"),
    ("APPLIED", "Beworben", "applied"),
    ("INTERVIEWS", "Interviews", "hr"),
    ("ARCHIVED", "Archiviert", "rejected"),
]
```

Jede Kategorie bekommt ein eigenes `seen_ids = set()` — bewusst **nicht** geteilt, damit ARCHIVED denselben Job überschreiben kann.

**2FA-Flow:** `_handle_2fa_checkpoint()` pollt URL:
- Option A: Push-Notification auf Handy → LinkedIn redirectet weg von `/checkpoint/` → auto-erkannt
- Option B: Code manuell via `/api/sync/linkedin/submit-2fa` eingeben

## `naechster_schritt`-Feld

Berechnetes Feld, wird **nicht** in der DB gespeichert. `_compute_naechster_schritt()` in `applications.py` läuft per GET-Request mit drei Extra-Queries:
- `next_interviews`: min(datum) future gespräch-Events
- `last_interviews`: max(datum) past gespräch-Events
- `max_event_dates`: max(datum) aller Events (≤ today, um Zukunftstermine auszuschließen)

## `letztes_update`

Der DB-Wert ist das manuelle Update-Datum. Im `GET /api/applications/`-Endpoint wird er in-memory durch `max(events.datum WHERE datum <= today)` überschrieben, falls größer — kein `db.commit()` dabei.

## Sync-Quellen und Kalender-Sonderregel

Kalenderquellen (`gcal`, `icloud_cal`) erzeugen **keine** Status-PendingMatches — nur Events.  
Guard in `sync_common.py`: `if source not in ('gcal', 'icloud_cal'):`

## CI/CD

GitHub Actions self-hosted runner auf dem Mac.  
Jobs: `backend` (ruff + pyright) → `frontend` (tsc + vite build) → `docker` (buildx).  
Deploy: Docker Buildx baut neue Images auf dem Runner, `docker compose up -d` rollt sie aus.

## Wichtige Konstanten

- `CURRENT_VERSION` in `frontend/src/components/ChangelogModal.tsx` — bei jeder inhaltlichen Änderung erhöhen
- OrbStack IPs: Backend `192.168.117.10`, Frontend `192.168.117.11`
- Fernet-Key-Datei: `backend/data/fernet.key` (wird beim ersten Start auto-generiert)

## Excel-Datei

Original: `/Users/eugengulinsky/Documents/Bewerbungen und Arbeitsverträge/Ich/Aktuell/Stellen/Bewerbungen_Eugen_Gulinsky.xlsx`  
Sheet: `Tracking`, 17 Spalten — Mapping in `models.py` unter `EXCEL_IMPORT_MAP` / `EXCEL_EXPORT_MAP`.
