# JobTracker – Projektstand

> **Historische Momentaufnahme vom 16. Juni 2026 (v2.0.17).** Für den laufend gepflegten, aktuellen technischen Stand siehe [ARCHITECTURE.md](ARCHITECTURE.md) — dort sind Router, Datenmodell und Diagramme immer auf dem neuesten Stand. Dieses Dokument bleibt als Snapshot der frühen Entwicklungsphase erhalten.

**Stand:** 16. Juni 2026 · **Version:** v2.0.17  
**Projekt-Ordner:** `/Users/eugengulinsky/code/jobtracker/`  
**GitHub:** https://github.com/EGulinsky/jobtracker (privat)  
**Excel-Quelldatei:** `Stellen/Bewerbungen_Eugen_Gulinsky.xlsx` (133 Einträge, Backup vorhanden)

---

## Was ist JobTracker?

Self-hosted Webanwendung als Ersatz für die Excel-Bewerbungsliste. Läuft lokal in OrbStack (Docker Compose). Ziel: Bewerbungsprozesse tracken, Kontakte verwalten, Gmail/Kalender/iCloud/LinkedIn synchronisieren, KI-gestützte Analyse.

**URL lokal:** `http://192.168.117.10` (OrbStack) oder `http://localhost:3000`  
**API / Swagger:** `http://localhost:8000/docs`

---

## Aktueller Entwicklungsstand

### Backend (Python 3.11 / FastAPI + SQLite)

#### Routers (alle unter `/api/...`)

| Datei | Prefix | Funktion |
|---|---|---|
| `applications.py` | `/api/applications` | CRUD Bewerbungen, Events, Kontakt-Verknüpfung; `naechster_schritt` berechnet |
| `contacts.py` | `/api/contacts` | Globale Kontaktverwaltung (n:m mit Bewerbungen) |
| `import_excel.py` | `/api/import/excel` | Multipart-Upload der xlsx, Status-Mapping |
| `export_excel.py` | `/api/export/excel` | Rückexport als xlsx |
| `settings.py` | `/api/settings` | AI-Provider-Konfiguration (verschlüsselt) |
| `calendar.py` | `/api/calendar` | Kalender-Events nach Datum (alle Event-Typen) |
| `sync_google.py` | `/api/sync/google` | Google OAuth 2.0 + Gmail + Calendar Sync |
| `sync_icloud.py` | `/api/sync/icloud` | iCloud Mail (IMAP), Calendar (CalDAV), Contacts (CardDAV) |
| `sync_targeted.py` | `/api/sync/targeted` | Pro-App-Sync über alle Quellen gleichzeitig |
| `sync_files.py` | `/api/sync/files` | Lokale Dokumente via files_bridge (Port 9998) |
| `sync_linkedin.py` | `/api/sync/linkedin` | LinkedIn Playwright-Scraper mit 2FA-Inline-Unterstützung |
| `sync_common.py` | – | Shared Helpers: AI-Klassifikation, Kontakt-Upsert, Dedup |
| `review.py` | `/api/review` | Review-Queue für KI-Vorschläge; cleanup-Endpoint für Kalender-Status |
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
| `FilesConfig` | Lokale Dokumente: Ordnerpfad + enabled |
| `CallsConfig` | Konfiguration für Anruflisten-Sync |

#### AI-Schicht (`app/ai/`)
- **`provider.py`**: Vendor-agnostisch via **LiteLLM** — Groq, Ollama, OpenAI-kompatibel. API-Keys Fernet-verschlüsselt.
- **`tasks.py`**: `classify_batch_for_app()` — klassifiziert Events in Batches

#### LinkedIn-Scraper (`sync_linkedin.py`)
- Headless Chromium via Playwright (separates `Dockerfile.playwright-base` — wird nur bei Playwright-Update neu gebaut)
- Scraped 5 Kategorien: SAVED / IN_PROGRESS / APPLIED / INTERVIEWS / ARCHIVED
- JS-basierte Job-Extraktion (stabil gegen CSS-Änderungen)
- **2FA**: Push-Notification auto-erkannt (URL-Polling) oder manueller Code via `/submit-2fa`
- **Archived → abgesagt**: Immer, unabhängig vom bisherigen Status
- **Bug (behoben v2.0.17):** `seen_ids` war global geteilt → ARCHIVED wurde durch APPLIED-Pass überschrieben. Jetzt per-Kategorie.

#### JobTracker Agent (`agent/`, läuft auf dem Mac, nicht in Docker)

Ein einzelner Hintergrund-Dienst (Port 9996, Bearer-Token-Auth) ersetzt die
früheren drei separaten Bridge-Skripte (`files_bridge.py`, `calls_bridge.py`,
`notes_bridge.py` — entfernt v3.27.0). Als `.app`/`.dmg` installierbar
(`agent/packaging/`), Menüleisten-Icon, registriert sich beim ersten Start
selbst als `launchd`-LaunchAgent (Autostart + Neustart bei Absturz).
OS-Adapter-Grenze (`agent/providers/`) für einen geplanten Windows-Port.
Details: [agent/README.md](../agent/README.md).

| Modul | Funktion |
|---|---|
| Dateien | Lokale Bewerbungsunterlagen (PDF, DOCX, TXT, MD), Backup-Dateizugriff |
| Anrufe | iPhone-Anrufliste (CallHistoryDB) + WhatsApp-Anrufe |
| Notizen | iCloud-Notizen via AppleScript (JXA) |

---

### Frontend (React 18 + Vite + TypeScript + Tailwind)

#### Komponenten

| Datei | Funktion |
|---|---|
| `App.tsx` | Hauptkomponente: Dashboard, Filter, View-Switching |
| `ApplicationTable.tsx` | Sortierbare Tabelle mit "Nächster Schritt"-Spalte (farbkodiert) |
| `KanbanBoard.tsx` | Drag & Drop Kanban nach `main_status`-Spalten (dnd-kit) |
| `ApplicationModal.tsx` | Detail/Edit-Modal: Status, Lifecycle-Bar, Kontakte, Timeline |
| `CalendarView.tsx` | Outlook-ähnliche Kalenderansicht: Tag / Arbeitswoche / Woche / Monat |
| `StatusBadge.tsx` | Farbige Badges für main_status + sub_status |
| `StatusPopover.tsx` | Inline-Dropdown zum Statuswechsel direkt in der Tabelle |
| `ContactsView.tsx` | CRM-Kontaktliste mit Verknüpfung zu Bewerbungen |
| `StatsBar.tsx` | KPI-Kacheln: Gesamt / Aktiv / Abgesagt / Interview-Rate |
| `ImportButton.tsx` | Excel-Upload |
| `ExportButton.tsx` | Excel-Download |
| `SyncButton.tsx` | Globaler Sync-Trigger mit Sync-Steuerung (Quellen ein-/ausschalten) |
| `LinkedInSyncButton.tsx` | LinkedIn-Sync mit 2FA-Inline-Dialog (amber Box für Code-Eingabe) |
| `ReviewModal.tsx` | Review-Inbox: KI-Vorschläge freigeben oder ablehnen |
| `SettingsModal.tsx` | Einstellungen (Sidebar-Layout): Google / iCloud / LinkedIn / Dokumente |
| `AiSettingsModal.tsx` | AI-Provider wählen (Groq/Ollama/OpenAI), API-Key, Test |
| `ChangelogModal.tsx` | Versionsverlauf; `CURRENT_VERSION` hier pflegen |
| `CleanupModal.tsx` | Dubletten bereinigen |

---

## Statusmodell (zweistufig)

**Alt (MVP):** Flache Enum (`applied`, `hr_scheduled`, `hr_done`, ...)  
**Aktuell:** `main_status` + optionaler `sub_status`

```
main_status:  prospecting | applied | hr | fb | waiting | negotiating | signed | rejected
sub_status:   1_scheduled | 1_done | 2_scheduled | 2_done | 3_scheduled | 3_done | ...
              (nur bei hr und fb)
```

Beispiel: `hr + 2_done` = „HR-Gespräch, 2. Runde geführt"

Excel-Import-Map: `EXCEL_IMPORT_MAP` in `models.py`  
Excel-Export-Map: `EXCEL_EXPORT_MAP` in `models.py`

---

## Deployment

```bash
# Starten (OrbStack muss laufen)
cd /Users/eugengulinsky/code/jobtracker
docker compose up -d

# Rebuild nach Code-Änderungen (CI/CD macht das automatisch)
docker compose up -d --build

# JobTracker Agent (separat, auf dem Mac) — installiert als .app, läuft dauerhaft
# im Hintergrund (Menüleiste), kein manueller Start nötig. Siehe agent/README.md.
```

**Docker-Services:**
- `backend` – FastAPI auf Port 8000, Volume `jobtracker-data` für SQLite + Fernet-Key
- `frontend` – Nginx mit React-Build auf Port 3000, proxyt `/api/*` → Backend

**CI/CD:** GitHub Actions self-hosted runner (auf dem Mac)
- `backend` → ruff Lint + pyright
- `frontend` → tsc + vite build
- `docker` → Docker Buildx, Deploy via `docker compose up -d`

---

## Implementiert (aktueller Stand)

- [x] FastAPI Backend mit SQLite (WAL)
- [x] Alle CRUD-Endpunkte für Bewerbungen + Events + Kontakte
- [x] Excel-Import (133 Einträge, Status-Mapping)
- [x] Excel-Export (Originalformat, 17 Spalten)
- [x] React Frontend (Tabelle, Kanban, Kalender, Kontakte)
- [x] Zweistufiges Statusmodell (main_status + sub_status)
- [x] Lifecycle-Bar im Detail-Modal
- [x] KPI-Kacheln (StatsBar)
- [x] Drag & Drop Kanban (dnd-kit)
- [x] Kalender-Ansicht (Outlook-Stil: Tag/Woche/Monat)
- [x] „Nächster Schritt" – intelligentes berechnetes Feld
- [x] Google OAuth 2.0 + Gmail + Google Calendar Sync
- [x] iCloud Mail (IMAP) + Kalender (CalDAV) + Kontakte (CardDAV) Sync
- [x] LinkedIn Playwright-Scraper (Session-gecacht, Archived→abgesagt, 2FA inline)
- [x] Lokale Dokumente/Notizen/Anrufe Sync über den JobTracker Agent (agent/)
- [x] AI-Klassifikation via LiteLLM (Groq, Ollama, OpenAI-kompatibel)
- [x] Review-Queue für KI-Vorschläge
- [x] Sync-Steuerung: Quellen ein-/ausschaltbar
- [x] Pro-App Targeted Sync
- [x] Kontakt-CRM (n:m mit Bewerbungen, Kontakt-Upsert aus Sync)
- [x] Fernet-Verschlüsselung für alle Credentials
- [x] Hintergrund-Sync-Loop (alle 20 Minuten, asyncio)
- [x] CI/CD (GitHub Actions, self-hosted runner)
- [x] Versionsverlauf (ChangelogModal, CURRENT_VERSION)
- [x] Dubletten-Bereinigung

---

## Was noch fehlt / Nächste Schritte

- [ ] **Analytics-Seite**: KPI-Charts, Funnel, Quellen-Effektivität (Recharts)
- [ ] **Alembic-Migrationen**: Aktuell `create_all()` beim Start; beim nächsten Schema-Breaking-Change nötig
- [ ] **Auth**: Kein Login für MVP (Single-User lokal)
- [ ] **CORS einschränken**: Aktuell `allow_origins=["*"]`
- [ ] **JobTracker Agent Windows-Port**: Architektur ist plattformübergreifend angelegt (Provider-Interfaces in `agent/providers/`), Windows-Adapter noch nicht implementiert

---

## Dateistruktur

```
/Users/eugengulinsky/code/jobtracker/
├── CLAUDE.md                          ← Claude Code Kontext (wird auto-gelesen)
├── README.md                          ← Quick-Start
├── docker-compose.yml
├── agent/                              ← JobTracker Agent (Mac-Hintergrunddienst, ersetzt die alten Bridges)
├── .github/workflows/ci.yml           ← GitHub Actions CI/CD (self-hosted runner)
├── docs/
│   ├── ARCHITECTURE.md               ← Technische Architektur (aktuell)
│   ├── JobTracker_Projektstand.md    ← dieses Dokument
│   └── JobTracker_Konzept_Architektur.md  ← ursprüngliches Planungsdokument
├── backend/
│   ├── Dockerfile
│   ├── Dockerfile.playwright-base    ← Separates Chromium-Base-Image
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── models.py                  ← Alle ORM-Modelle + Status-Maps
│       ├── schemas.py
│       ├── database.py
│       ├── ai/
│       │   ├── provider.py            ← LiteLLM Wrapper (Fernet-Krypto)
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
