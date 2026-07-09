# rapport – Claude Code Kontext

Self-hosted Bewerbungs-Tracking-App (Ersatz für `Bewerbungen_Eugen_Gulinsky.xlsx`).  
Läuft lokal in OrbStack (Docker Compose). Aktueller Stand: siehe `CURRENT_VERSION` in `frontend/src/components/ChangelogModal.tsx`.

Vollständige, laufend gepflegte technische Doku inkl. Mermaid-Diagrammen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Projekt starten

```bash
# App starten (OrbStack / Docker muss laufen)
cd /Users/eugengulinsky/code/rapport
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
rapport/
├── CLAUDE.md · README.md · docker-compose.yml (Services: backend, frontend, seq)
│   docker-compose.test.yml    # Isolierte Testumgebung (eigene DB, Ports 3001/8001)
├── .github/workflows/ci.yml   # Jobs: backend, frontend, e2e, docker, deploy, notify-failure
├── docs/
│   ├── ARCHITECTURE.md         # Technische Architektur inkl. Mermaid-Diagrammen
│   └── TEST_KONZEPT.md         # Testkonzept (Phase 1–4 abgeschlossen, Phase 5 E2E gestartet)
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
│   ├── src/ (s.u.)
│   ├── e2e/                    # Playwright-E2E-Tests (Phase 5)
│   │   ├── playwright.config.ts
│   │   ├── fixtures.ts         # authToken-Fixture (E2E_USER via /api/e2e/setup-user)
│   │   └── *.spec.ts           # User-Journey-Tests
│   ├── Dockerfile.e2e          # mcr.microsoft.com/playwright als Base
│   └── nginx.conf · nginx.test.conf
└── frontend/src/
    ├── App.tsx · types.ts · api/client.ts
    └── components/  ApplicationTable · KanbanBoard · ApplicationModal · …
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
    ("DRAFT", "Entwurf", "prospecting"),
    ("CLICKED_APPLY", "Beworben (unbestätigt)", "prospecting"),
    ("APPLIED", "Beworben", "applied"),
    ("INTERVIEWS", "Interviews", "hr"),
    ("ARCHIVED", "Archiviert", "rejected"),
]
```
LinkedIns Sammel-Tab "In Progress" ist nur eine Client-Ansicht von DRAFT + CLICKED_APPLY — `?stage=in-progress` liefert immer eine leere Seite, die echten Slugs sind `draft` und `clicked_apply`.

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
Jobs: `backend` (ruff + pyright + `pytest -m "unit or component or api"`, 447 Tests) → `frontend` (tsc + vite build) → `e2e` (Playwright via docker-compose.test.yml, main-Push + workflow_dispatch) → `docker` (buildx, wartet auf e2e) → `deploy` (self-hosted). Zusätzlich laufen bei Push auf `main` 93 L3-Integrationstests (`pytest -m integration`).  
Deploy: `git pull` → Docker Buildx baut neue Images auf dem Runner → `docker compose up -d --build` → Health-Poll → macOS-Notification. Details: [docs/TEST_KONZEPT.md](docs/TEST_KONZEPT.md) (Testkonzept, Phase 1–4 abgeschlossen, Phase 5 E2E gestartet).  
Push auf `main` löst immer Test+Deploy aus. Manuell (z.B. auf einem Feature-Branch) per `gh workflow run ci.yml --ref <branch>` nur testen, oder mit `-f deploy=true` zusätzlich deployen (deployt dabei immer den `main`-Head, unabhängig vom gewählten `--ref`).

## Wichtige Konstanten

- `CURRENT_VERSION` in `frontend/src/components/ChangelogModal.tsx` — bei jeder inhaltlichen Änderung erhöhen
- OrbStack IPs: Backend `192.168.117.10`, Frontend `192.168.117.11`
- Fernet-Key-Datei: `backend/data/fernet.key` (wird beim ersten Start auto-generiert)

## Rapport Agent (`agent/`)

Läuft als natives macOS-launchd-Programm **außerhalb** von Docker (Menüleisten-App, Port 9996) — `docker compose up -d --build` fasst ihn nicht an. Code-Änderungen in `agent/` brauchen einen echten Rebuild + Neuinstallation:
```bash
cd agent && python3 -m venv .venv_build && .venv_build/bin/pip install -r packaging/requirements-packaging.txt
PATH="$PWD/.venv_build/bin:$PATH" packaging/build_dmg.sh <version>
```
Danach alten launchd-Job entladen (`launchctl unload -w ~/Library/LaunchAgents/com.rapport.agent.plist`), neue App nach `/Applications` kopieren, einmal öffnen (self-registriert). Config/Token liegt in `~/Library/Application Support/RapportAgent/config.json` — bleibt bei App-Updates erhalten, solange der Ordner nicht gelöscht wird.

## E2E-Tests (Playwright)

E2E-Tests laufen im isolierten Test-Stack (`docker-compose.test.yml`):
```bash
# Test-Stack starten + E2E-Tests ausführen
docker compose -p rapport-test -f docker-compose.test.yml up -d --build backend-test frontend-test
# Warten bis Backend bereit, dann:
docker compose -p rapport-test -f docker-compose.test.yml run --rm e2e-runner
# Aufräumen
docker compose -p rapport-test -f docker-compose.test.yml down -v
```

Test-Dateien in `frontend/e2e/`. Basis-Fixture (`fixtures.ts`) registriert einen E2E-Testnutzer
über `POST /api/e2e/setup-user` (nur aktiv bei `E2E_TESTING=true`). Der Auth-Token wird
in `localStorage` gesetzt, danach lädt die App als authentifizierter Nutzer.

## Excel-Datei

Original: `/Users/eugengulinsky/Documents/Bewerbungen und Arbeitsverträge/Ich/Aktuell/Stellen/Bewerbungen_Eugen_Gulinsky.xlsx`  
Sheet: `Tracking`, 17 Spalten — Mapping in `models.py` unter `EXCEL_IMPORT_MAP` / `EXCEL_EXPORT_MAP`.

## Nächste Schritte (Testkonzept Phase 5)

Aktueller Stand v3.48.0 — **Phase 5 abgeschlossen** (12/12 E2E-Journeys). Nächster Schritt: Phase-4-Lücke (LinkedIn-Playwright-Fixture-Replay).

**E2E-Journeys:**

| # | Journey | Status |
|---|---------|--------|
| 1 | Application Lifecycle (anlegen → Statuswechsel → ablehnen) | ✅ |
| 2 | Kanban Drag & Drop ändert Status inkl. Sub-Status-Reset | ✅ |
| 3 | LinkedIn-Link importieren → Formular vorausgefüllt → speichern | ✅ |
| 4 | Bereinigen-Button kontextabhängig (Vorschau → Ausführen) | ✅ |
| 5 | Merge-Dialog (Bewerbungen via Tabellenansicht) | ✅ |
| 6 | Targeted-Sync für eine Bewerbung (gemockte Quellen) | ✅ |
| 7 | Manuelle Kandidatenzuordnung (Suche → Multiselect → Import) | ✅ |
| 8 | KI-Bewertung: "Neu bewerten" → Ampel + Reasoning | ✅ |
| 9 | Batch-KI-Bewertung mit Live-Fortschritt (+ Rate-Limit-Simulation) | ✅ |
| 10 | Firmen-Sync mit Markierung (nur Auswahl) | ✅ |
| 11 | Backup konfigurieren → manueller Lauf → Restore | ✅ |
| 12 | Excel-Import (Originalformat) → Export → Round-Trip-Vergleich | ✅ |

**Phase-4-Lücke:** `linkedin_job_description.py` bei 0 % Coverage (LinkedIn-Playwright-Fixure-Replay,
für Phase 6 vorgemerkt). Kann jederzeit nachgeholt werden, bevor Phase 5 abgeschlossen ist.

**Hinweise für die Implementierung:**
- E2E-Tests in `frontend/e2e/` ablegen, Muster in `application-lifecycle.spec.ts` folgen
- `test.beforeEach` in der Datei oder `test.describe.configure` für Setup nutzen
- `authToken`-Fixture registriert automatisch einen E2E-Testnutzer
- Selektoren nach Text/Inhalt (keine `data-testid` im Projekt)
- Für gemockte externe Quellen: Playwright `page.route()`-Interception nutzen
- Neuen Test in der bestehenden `.spec.ts`-Datei oder als separate Datei anlegen
