# JobTracker – Claude Code Kontext

Self-hosted Bewerbungs-Tracking-App (Ersatz für `Bewerbungen_Eugen_Gulinsky.xlsx`).  
Läuft lokal in OrbStack (Docker Compose). Aktueller Stand: siehe `CURRENT_VERSION` in `frontend/src/components/ChangelogModal.tsx`.

Vollständige, laufend gepflegte technische Doku inkl. Mermaid-Diagrammen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

Detaillierte, gepflegte Übersicht (Router, Komponenten, Datenmodell): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#1-system--und-sw-architektur). Kurzfassung:

```
jobtracker/
├── CLAUDE.md · README.md · docker-compose.yml (Services: backend, frontend, seq)
├── .github/workflows/ci.yml     # ruff + tsc + docker buildx, self-hosted runner + deploy
├── docs/ARCHITECTURE.md         # Technische Architektur inkl. Mermaid-Diagrammen
├── backend/app/
│   ├── main.py · database.py · models.py · schemas.py
│   ├── audit.py · dedup.py · logger.py · linkedin_job_description.py
│   ├── ai/{provider,tasks}.py
│   └── routers/  applications · contacts · companies · merge · cleanup ·
│                 import_excel · export_excel · export_pdf · attachments ·
│                 settings · calendar · analytics · audit_log · backup ·
│                 sync_{common,google,icloud,targeted,files,linkedin,company} ·
│                 review · startup_check
└── frontend/src/
    ├── App.tsx · types.ts · api/client.ts
    └── components/  ApplicationTable · KanbanBoard · ApplicationModal ·
                      CalendarView · StatsBar · StatusBadge/Popover ·
                      ContactsView/Modal · CompaniesView/Modal/Logo/FilterPicker ·
                      MergeDialog · CleanupModal · ReviewModal · SettingsModal ·
                      SyncButton · Import/Export/PdfExportButton · AuditLogModal ·
                      AnalyticsView · ChangelogModal · StartupWarningBanner
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
