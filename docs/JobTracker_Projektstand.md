# JobTracker – Projektstand & Handoff-Dokument

**Stand:** 13. Juni 2026  
**Projekt-Ordner:** `/Users/eugengulinsky/code/jobtracker/`  
**GitHub:** https://github.com/EGulinsky/jobtracker (privat)  
**Zugehörige Excel:** `Stellen/Bewerbungen_Eugen_Gulinsky.xlsx` (133 Einträge, Backup vorhanden)

---

## Was ist JobTracker?

Self-hosted Webanwendung als Ersatz für die Excel-Bewerbungsliste. Läuft lokal in OrbStack (Docker Compose). Ziel: Bewerbungsprozesse tracken, Kontakte verwalten, Gmail/Kalender/iCloud synchronisieren, KI-gestützte Analyse.

**URL lokal:** `http://localhost:3000` oder `http://jobtracker-frontend.orb.local`  
**API / Swagger:** `http://localhost:8000/docs`

---

## Aktueller Entwicklungsstand

### Backend (Python / FastAPI + SQLite)

#### Routers (alle unter `/api/...`)
| Datei | Prefix | Funktion |
|---|---|---|
| `applications.py` | `/api/applications` | CRUD Bewerbungen, Events, Kontakt-Verknüpfung |
| `contacts.py` | `/api/contacts` | Globale Kontaktverwaltung (n:m mit Bewerbungen) |
| `import_excel.py` | `/api/import/excel` | Multipart-Upload der xlsx, Status-Mapping |
| `export_excel.py` | `/api/export/excel` | Rückexport als xlsx |
| `settings.py` | `/api/settings` | AI-Provider-Konfiguration (verschlüsselt) |
| `sync_google.py` | `/api/sync/google` | Google OAuth 2.0 + Gmail + Calendar Sync |
| `sync_icloud.py` | `/api/sync/icloud` | iCloud Mail (IMAP), Calendar (CalDAV), Contacts (CardDAV), Notes |
| `sync_targeted.py` | `/api/sync/targeted` | Pro-App-Sync über alle Quellen gleichzeitig |
| `sync_linkedin.py` | `/api/sync/linkedin` | LinkedIn Playwright-Scraper (Session-Cookies gecacht) |
| `sync_common.py` | – | Shared Helpers: AI-Klassifikation, Kontakt-Upsert, Dedup |
| `review.py` | `/api/review` | KI-gematchte Vorschläge zur Nutzerfreigabe |
| `cleanup.py` | `/api/cleanup` | Dubletten-Bereinigung und Datenpflege |

#### Datenbankmodelle (SQLite, auto-erstellt beim Start)
| Modell | Beschreibung |
|---|---|
| `Application` | Bewerbung mit `main_status` + `sub_status` |
| `Contact` | Kontaktperson, n:m mit Bewerbungen über Join-Table |
| `Event` | Interaktion (Mail, Anruf, Notiz, Kalender), mit `source`-Feld |
| `GoogleSync` | Google OAuth-Credentials (Fernet-verschlüsselt) |
| `ICloudSync` | iCloud App-Passwort (Fernet-verschlüsselt), IMAP/CalDAV |
| `PendingMatch` | KI-vorgeschlagene Zuordnungen, warten auf Nutzerfreigabe |
| `SyncedItem` | Dedup-Tabelle für bereits verarbeitete externe IDs |
| `AiSettings` | AI-Provider-Konfiguration (LiteLLM, Groq, Ollama etc.) |
| `LinkedInSync` | LinkedIn-Credentials + gecachte Session-Cookies |
| `CallsConfig` | Konfiguration für Anruflisten-Sync |

#### AI-Schicht (`app/ai/`)
- **`provider.py`**: Vendor-agnostisch via **LiteLLM** — unterstützt Groq, Ollama, OpenAI-kompatible Anbieter. API-Keys Fernet-verschlüsselt in `data/fernet.key`.
- **`tasks.py`**: AI-Aufgaben (Matching, Zusammenfassungen, Analyse)

#### Bridge-Skripte (laufen auf dem Mac, nicht in Docker)
| Skript | Port | Funktion |
|---|---|---|
| `calls_bridge.py` | 9997 | Liest iPhone-Anrufliste (`CallHistoryDB`) + WhatsApp-Anrufe, HTTP GET `/calls` |
| `notes_bridge.py` | 9999 | Liest iCloud-Notizen via AppleScript (JXA), HTTP GET `/notes` |

Beide müssen separat im Terminal gestartet werden: `python3 calls_bridge.py` / `python3 notes_bridge.py`

---

### Frontend (React 18 + Vite + TypeScript + Tailwind)

#### Komponenten
| Datei | Funktion |
|---|---|
| `App.tsx` | Hauptkomponente: Dashboard, Filter, View-Switching |
| `ApplicationTable.tsx` | Sortierbare Tabelle mit inline StatusPopover |
| `KanbanBoard.tsx` | Kanban nach `main_status`-Spalten |
| `ApplicationModal.tsx` | Detail/Edit-Modal: Status, Kontakte, Events, Gesprächsnotizen |
| `StatusBadge.tsx` | Farbige Badges für main_status + sub_status |
| `StatusPopover.tsx` | Inline-Dropdown zum Statuswechsel direkt in der Tabelle |
| `ContactsView.tsx` | CRM-Kontaktliste mit Verknüpfung zu Bewerbungen |
| `StatsBar.tsx` | KPI-Kacheln: Gesamt / Aktiv / Abgesagt / Interview-Rate |
| `ImportButton.tsx` | Excel-Upload |
| `ExportButton.tsx` | Excel-Download |
| `SyncButton.tsx` | Auslöser für Google/iCloud-Sync |
| `ReviewModal.tsx` | Review-Inbox: KI-Vorschläge freigeben oder ablehnen |
| `SettingsModal.tsx` | Google OAuth + iCloud-Zugangsdaten konfigurieren |
| `AiSettingsModal.tsx` | AI-Provider wählen (Groq/Ollama/OpenAI), API-Key eingeben, Test |
| `CleanupModal.tsx` | Dubletten bereinigen |

---

### Kritische Architektur-Entscheidung: Zweistufiges Status-Modell

**Alt (MVP):** Flache Enum mit 11 Werten (`applied`, `hr_scheduled`, `hr_done`, ...)  
**Neu (Claude Code):** `main_status` + optionaler `sub_status`

```
main_status  Werte: prospecting | applied | hr | fb | waiting | negotiating | signed | rejected
sub_status   Werte: 1_scheduled | 1_done | 2_scheduled | 2_done | 3_scheduled | 3_done | ...
```

Beispiel: `hr + 2_done` = „HR-Gespräch, 2. Runde geführt"

Die Migrations-Map für alte Flat-Status ist in `models.py` unter `OLD_STATUS_MIGRATION` definiert.  
Die Excel-Import-Map ist unter `EXCEL_IMPORT_MAP`, der Export unter `EXCEL_EXPORT_MAP`.

---

## Deployment

```bash
# Starten (OrbStack muss laufen)
cd /Users/eugengulinsky/code/jobtracker
docker compose up -d

# Stoppen
docker compose down

# Rebuild nach Code-Änderungen
docker compose up -d --build

# Bridge-Skripte (separat, auf dem Mac)
python3 calls_bridge.py   # Port 9997
python3 notes_bridge.py   # Port 9999
```

**Docker Compose Services:**
- `backend` – FastAPI auf Port 8000, Volume `jobtracker-data` für SQLite + Fernet-Key
- `frontend` – Nginx mit React-Build auf Port 3000, proxyt `/api/*` → Backend

**CI/CD:** GitHub Actions (`.github/workflows/ci.yml`)
- `backend`-Job: ruff Lint + pyright (bei jedem Push/PR auf main)
- `frontend`-Job: tsc + vite build
- `docker`-Job: Docker Buildx für beide Images (nur bei Push auf main)

---

## Integrations-Setup (noch zu konfigurieren)

### Google (Gmail + Calendar)
1. Google Cloud Console → neue App → OAuth 2.0 Client (Web)
2. Redirect URI: `http://localhost:8000/api/sync/google/callback`
3. In JobTracker → Einstellungen → Google: Client ID + Secret eintragen
4. OAuth-Flow starten → Gmail + Calendar werden gescannt

### iCloud (Mail + Kalender + Kontakte + Notizen)
1. Apple ID → Sicherheit → App-spezifische Passwörter → neues Passwort generieren
2. In JobTracker → Einstellungen → iCloud: Apple-ID + App-Passwort eintragen
3. Sync für Mail (IMAP), Kalender (CalDAV), Kontakte (CardDAV), Notizen starten

### AI-Provider
- **Groq** (empfohlen, kostenlos): API-Key von [console.groq.com](https://console.groq.com), Modell `groq/llama-3.3-70b-versatile`
- **Ollama** (lokal, kein API-Key): Base URL `http://host.docker.internal:11434`
- Einstellungen unter: JobTracker → ⚙ → AI-Provider

### Anrufliste (calls_bridge.py)
Benötigt **Full Disk Access** für Terminal in macOS:  
Systemeinstellungen → Datenschutz & Sicherheit → Festplattenvollzugriff → Terminal ✓

---

## Was noch fehlt / Nächste Schritte

- [x] **LinkedIn-Sync**: `sync_linkedin.py` implementiert (Playwright, Session-Cookies gecacht)
- [ ] **Analytics-Seite**: KPI-Charts, Funnel, Quellen-Effektivität (Recharts)
- [ ] **Alembic-Migrationen**: Aktuell `create_all()` beim Start, Schema noch in Bewegung
- [ ] **Auth**: Kein Login für MVP (Single-User lokal), JWT + Google-Login für Phase 3
- [ ] **CORS einschränken**: Aktuell `allow_origins=["*"]`
- [ ] **Review-Flow testen**: PendingMatch-Tabelle + ReviewModal vorhanden, End-to-End noch offen
- [ ] **calls_bridge.py**: Erfordert macOS Full Disk Access, noch nicht produktiv getestet

---

## Dateistruktur

```
/Users/eugengulinsky/code/jobtracker/        ← Projektordner (GitHub: EGulinsky/jobtracker)
├── CLAUDE.md                                ← Claude Code Kontext (wird auto-gelesen)
├── README.md                                ← Quick-Start
├── JobTracker_Projektstand.md               ← dieses Dokument
├── docker-compose.yml
├── calls_bridge.py                          ← Mac-Bridge für Anrufe (Port 9997)
├── notes_bridge.py                          ← Mac-Bridge für Notizen (Port 9999)
├── .github/workflows/ci.yml                 ← GitHub Actions CI/CD
├── .vscode/                                 ← VS Code Projekt-Einstellungen
├── docs/
│   └── ARCHITECTURE.md                      ← Technische Architektur-Doku
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py                        ← Alle ORM-Modelle + Status-Maps
│   │   ├── schemas.py
│   │   ├── database.py
│   │   ├── ai/
│   │   │   ├── provider.py                  ← LiteLLM Wrapper (Fernet-Krypto)
│   │   │   └── tasks.py
│   │   └── routers/
│   │       ├── applications.py
│   │       ├── contacts.py
│   │       ├── import_excel.py
│   │       ├── export_excel.py
│   │       ├── settings.py
│   │       ├── sync_google.py
│   │       ├── sync_icloud.py
│   │       ├── sync_targeted.py             ← Pro-App-Sync (alle Quellen)
│   │       ├── sync_linkedin.py             ← LinkedIn Playwright-Scraper
│   │       ├── sync_common.py               ← Shared helpers
│   │       ├── review.py
│   │       └── cleanup.py
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.tsx
        ├── types.ts                         ← main_status + sub_status Typen
        ├── api/client.ts
        └── components/
            ├── ApplicationTable.tsx
            ├── ApplicationModal.tsx         ← inkl. Lifecycle-Bar
            ├── KanbanBoard.tsx
            ├── ContactsView.tsx
            ├── ReviewModal.tsx
            ├── SettingsModal.tsx
            ├── AiSettingsModal.tsx
            ├── SyncButton.tsx (SyncPanel)
            ├── StatusBadge.tsx
            ├── StatusPopover.tsx
            ├── StatsBar.tsx
            ├── ImportButton.tsx
            ├── ExportButton.tsx
            └── CleanupModal.tsx
```
