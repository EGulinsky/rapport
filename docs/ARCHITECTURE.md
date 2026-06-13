# JobTracker – Technische Architektur

## Inhaltsverzeichnis

1. [System- und SW-Architektur](#1-system--und-sw-architektur)
2. [API-Schnittstellen (intern)](#2-api-schnittstellen-intern)
3. [Externe Schnittstellen (Sync-Quellen)](#3-externe-schnittstellen-sync-quellen)
4. [Statusübergänge](#4-statusübergänge)
5. [Workflows](#5-workflows)
6. [Datenmodell](#6-datenmodell)

---

## 1. System- und SW-Architektur

### Überblick

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Compose                         │
│                                                             │
│  ┌──────────────────┐          ┌───────────────────────┐   │
│  │  frontend        │          │  backend              │   │
│  │  (nginx:alpine)  │◄────────►│  (Python 3.11/uvicorn)│   │
│  │  Port 3000       │  REST    │  Port 8000            │   │
│  │  React + TS      │  JSON    │  FastAPI              │   │
│  └──────────────────┘          └──────────┬────────────┘   │
│                                           │                  │
│                                  ┌────────▼────────┐        │
│                                  │  SQLite (WAL)   │        │
│                                  │  jobtracker.db  │        │
│                                  │  Volume: -data  │        │
│                                  └─────────────────┘        │
└─────────────────────────────────────────────────────────────┘

Externe Dienste (optional, per Sync-Konfiguration):
  Gmail API  ──►  OAuth 2.0  ──►  Google Cloud Project
  GCal API   ──►  OAuth 2.0  ──►  (gleiche Credentials)
  iCloud Mail ─►  IMAP :993  ──►  imap.mail.me.com
  iCloud Cal  ─►  CalDAV     ──►  caldav.icloud.com
  LinkedIn    ─►  Playwright ──►  linkedin.com (headless)
  Calls       ─►  HTTP-Bridge──►  localhost:9988 (macOS-App)
```

### Technologie-Stack

| Schicht | Technologie | Version |
|---|---|---|
| Frontend-Framework | React | 18 |
| Frontend-Sprache | TypeScript | 5 |
| Frontend-Styles | Tailwind CSS | 3 |
| Frontend-Build | Vite | 5 |
| Frontend-Serving | nginx (Alpine) | stable |
| Backend-Framework | FastAPI | 0.110+ |
| Backend-Sprache | Python | 3.11 |
| Backend-Server | uvicorn | 0.29+ |
| ORM | SQLAlchemy | 2.0 |
| Datenbank | SQLite (WAL-Modus) | 3 |
| Kryptographie | cryptography (Fernet) | 42+ |
| AI-Klassifikation | litellm (Provider-unabhängig) | latest |
| Excel-Import/Export | openpyxl | 3.1+ |
| LinkedIn-Scraper | Playwright | latest |
| Containerisierung | Docker Compose | v2 |

### Container-Konfiguration

**`docker-compose.yml`** definiert zwei Services:

| Service | Image | Port | Volumes |
|---|---|---|---|
| `backend` | `./backend` Dockerfile | `8000:8000` | `jobtracker-data:/app/data` |
| `frontend` | `./frontend` Dockerfile | `3000:80` | – |

Beide Container erhalten `TZ=Europe/Berlin` als Umgebungsvariable, damit Zeitstempel in CEST korrekt dargestellt werden.

Das SQLite-File liegt im benannten Volume `jobtracker-data` unter `/app/data/jobtracker.db`. Das Schema wird beim Start via `SQLAlchemy create_all()` angelegt – kein Migrationstool.

### Projektstruktur (Backend)

```
backend/app/
├── main.py              FastAPI-App, CORS, Lifespan, Router-Registration
├── database.py          SQLAlchemy-Engine + SessionLocal + get_db-Dependency
├── models.py            ORM-Modelle, Enums, Status-Mappings
├── schemas.py           Pydantic Request/Response-Schemas
├── ai/
│   ├── provider.py      litellm-Wrapper, Fernet-Kryptographie, AINotConfigured
│   └── tasks.py         classify_batch_for_app(), BATCH_SIZE
└── routers/
    ├── applications.py  CRUD + Events + Contacts pro Bewerbung
    ├── contacts.py      Globale Kontaktverwaltung
    ├── import_excel.py  POST /api/import/excel
    ├── export_excel.py  GET /api/export/excel
    ├── settings.py      AI-Settings + Sync-Konfiguration lesen/schreiben
    ├── sync_common.py   Shared helpers: dedup, AI-Klassifikation, Kontakt-Upsert
    ├── sync_google.py   Google OAuth + Gmail + GCal
    ├── sync_icloud.py   iCloud IMAP + CalDAV + CardDAV
    ├── sync_targeted.py Pro-App-Sync für alle Quellen
    ├── sync_linkedin.py LinkedIn Playwright-Scraper
    ├── review.py        Manuelle Review-Queue (PendingMatches)
    └── cleanup.py       Datenbereinigung
```

### Projektstruktur (Frontend)

```
frontend/src/
├── App.tsx                 Root-Komponente: Filter, Tabs, Views
├── types.ts                TypeScript-Typen, Status-Labels/Farben, Konstanten
├── api/client.ts           Fetch-Wrapper für alle Backend-Calls
└── components/
    ├── ApplicationTable.tsx   Sortierbare Tabellenansicht
    ├── KanbanBoard.tsx        Kanban-Ansicht nach Status-Spalten
    ├── ApplicationModal.tsx   Detail/Edit-Modal mit Lifecycle-Bar + Timeline
    ├── StatsBar.tsx           KPI-Kacheln oben
    ├── StatusBadge.tsx        Farbige Status-Badges
    ├── ImportButton.tsx       Excel-Upload
    ├── ExportButton.tsx       Excel-Download
    ├── ContactsView.tsx       Kontaktübersicht (sortierbar)
    └── SyncPanel.tsx          Sync-Konfiguration + Trigger
```

---

## 2. API-Schnittstellen (intern)

Swagger UI: `http://localhost:8000/docs`

### Bewerbungen

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/applications/` | Liste (Filter: `main_status`, `search`, `show_rejected`) |
| `GET` | `/api/applications/stats` | KPI-Zahlen (Gesamt/Aktiv/Abgesagt/Nach Status) |
| `GET` | `/api/applications/{id}` | Detail mit Events + Contacts |
| `POST` | `/api/applications/` | Neu anlegen (erstellt automatisch Event `bewerbung`) |
| `PATCH` | `/api/applications/{id}` | Felder aktualisieren (erstellt Event bei Statuswechsel) |
| `DELETE` | `/api/applications/{id}` | Löschen (kaskadiert Events + contact_application) |

### Events (Bewerbungs-Timeline)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/applications/{id}/events` | Alle Events (absteigend nach Datum) |
| `POST` | `/api/applications/{id}/events` | Event manuell hinzufügen |
| `PATCH` | `/api/applications/{id}/events/{eid}` | Event bearbeiten |
| `DELETE` | `/api/applications/{id}/events/{eid}` | Event löschen |

### Kontakte (pro Bewerbung)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/applications/{id}/contacts` | Kontakte dieser Bewerbung |
| `POST` | `/api/applications/{id}/contacts` | Kontakt anlegen + verknüpfen |
| `PATCH` | `/api/applications/{id}/contacts/{cid}` | Kontakt bearbeiten |
| `DELETE` | `/api/applications/{id}/contacts/{cid}` | Verknüpfung entfernen (Kontakt-Objekt bleibt, wenn andere Apps verknüpft) |

### Kontakte (global)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/contacts/` | Alle Kontakte (mit verknüpften Bewerbungen) |
| `GET` | `/api/contacts/{id}` | Einzelkontakt |
| `PATCH` | `/api/contacts/{id}` | Kontakt bearbeiten |
| `DELETE` | `/api/contacts/{id}` | Kontakt löschen |

### Import / Export

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/import/excel` | Excel-Upload (multipart/form-data, Sheet "Tracking") |
| `GET` | `/api/export/excel` | Excel-Download (`?show_rejected=true` optional) |

### Sync – Google

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/sync/google/credentials` | Client ID + Secret speichern |
| `GET` | `/api/sync/google/status` | Verbindungsstatus + letzte Sync-Zeiten |
| `GET` | `/api/sync/google/auth` | OAuth-Redirect-URL erzeugen |
| `GET` | `/api/sync/google/callback` | OAuth-Callback (CSRF-State-Check) |
| `POST` | `/api/sync/google/gmail/sync` | Gmail global synchronisieren (Background Task) |
| `POST` | `/api/sync/google/gcal/sync` | Google Calendar global synchronisieren |
| `DELETE` | `/api/sync/google/disconnect` | Credentials + Tokens löschen |

### Sync – iCloud

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/sync/icloud/credentials` | Apple ID + App-Passwort speichern |
| `GET` | `/api/sync/icloud/status` | Verbindungsstatus + letzte Sync-Zeiten |
| `POST` | `/api/sync/icloud/mail/sync` | iCloud Mail global synchronisieren |
| `POST` | `/api/sync/icloud/calendar/sync` | iCloud Kalender synchronisieren |
| `POST` | `/api/sync/icloud/contacts/sync` | iCloud Kontakte importieren |
| `POST` | `/api/sync/icloud/2fa/verify` | 2FA-Code einlösen |
| `DELETE` | `/api/sync/icloud/disconnect` | Credentials löschen |

### Sync – Targeted (Pro-App)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/sync/targeted/{app_id}` | Alle Quellen für eine Bewerbung synchronisieren |
| `GET` | `/api/sync/targeted/{app_id}/progress` | Sync-Fortschritt (SSE-ähnlich via Polling) |

### Sync – LinkedIn

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/sync/linkedin/credentials` | LinkedIn-Login speichern |
| `GET` | `/api/sync/linkedin/status` | Verbindungsstatus |
| `POST` | `/api/sync/linkedin/sync` | Alle aktiven Bewerbungen auf LinkedIn prüfen |

### Review-Queue

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/review/pending` | Offene PendingMatches |
| `POST` | `/api/review/{id}/approve` | Match bestätigen (Event oder Statuswechsel anlegen) |
| `POST` | `/api/review/{id}/reject` | Match verwerfen |

### Einstellungen + Hilfsfunktionen

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/settings/ai` | AI-Provider-Konfiguration lesen |
| `POST` | `/api/settings/ai` | AI-Provider-Konfiguration schreiben |
| `GET` | `/health` | Health-Check |

---

## 3. Externe Schnittstellen (Sync-Quellen)

### 3.1 Gmail API (Google OAuth 2.0)

- **Protokoll:** REST, `google-auth` + `google-api-python-client`
- **Scopes:** `gmail.readonly`, `calendar.readonly`
- **OAuth-Flow:** Standard Authorization Code Flow; Redirect URI `http://localhost:8000/api/sync/google/callback`
- **Tokens:** Access Token + Refresh Token Fernet-verschlüsselt in `google_sync.access_token_enc / refresh_token_enc`
- **Sync-Strategie (global):** Sucht nach Mails mit Schlüsselwörtern aller aktiven Bewerbungen seit `gmail_last_sync`
- **Sync-Strategie (targeted):** Gmail-Query `from:firma OR to:firma OR subject:firma` eingeschränkt auf Firmenname + Zielfirma; Rollenworte als OR-Clause
- **Dedup:** `synced_items` mit `source="gmail"` und Gmail Message-ID als `external_id`

### 3.2 Google Calendar API

- **Protokoll:** REST (gleiche Credentials wie Gmail)
- **Sync-Strategie:** Events aus allen Kalendern; Firma/Rolle als Suchbegriff im Titel/Beschreibung
- **Kontakt-Extraktion:** Alle Teilnehmer (`attendees`) werden via `upsert_contact_from_sender` angelegt/aktualisiert
- **Dedup:** `synced_items` mit `source="gcal"` und Event-ID

### 3.3 iCloud Mail (IMAP)

- **Host:** `imap.mail.me.com:993` (SSL)
- **Auth:** Apple App-Specific Password (Fernet-verschlüsselt in `icloud_sync.app_password_enc`)
- **IMAP-User:** `icloud_email` (muss `@icloud.com` oder `@me.com` sein, nicht generische Apple-ID)
- **Suche:** IMAP `SEARCH` mit `SUBJECT` / `FROM` Firma; Pro-App auch `SINCE` letzter Sync
- **Dedup:** `synced_items` mit `source="icloud_mail"` und MD5-Hash aus Message-ID + Subject

### 3.4 iCloud Calendar (CalDAV)

- **Server:** `https://caldav.icloud.com`
- **Protokoll:** CalDAV (XML-basiert), Library `vobject` für VCALENDAR-Parsing
- **Organizer/Attendees:** Aus VEVENT `organizer`/`attendee` Properties extrahiert; CN-Parameter = Anzeigename
- **Dedup:** `synced_items` mit `source="icloud_cal"` und UID des VEVENT

### 3.5 LinkedIn (Playwright)

- **Methode:** Headless-Browser-Scraping via `playwright`
- **Session:** Login-Cookies werden JSON-serialisiert in `linkedin_sync.session_cookies` gecacht
- **Sync:** Lädt Bewerbungsseite (`/my-items/saved-jobs`), prüft Status-Labels pro gespeicherter Stelle
- **Credentials:** Email + Fernet-verschlüsseltes Passwort in `linkedin_sync`

### 3.6 Calls Bridge (macOS-App)

- **Protokoll:** HTTP, lokal auf `localhost:9988`
- **Funktion:** Liest Anruflisten aus der macOS Phone-App via AppleScript-Bridge
- **Matching:** Rufnummer → Kontakt → Bewerbung via Telefonnummern-Index
- **Konfiguration:** `calls_config.enabled`; kein Token nötig (lokal)

### 3.7 AI-Klassifikation (litellm)

- **Zweck:** Mail/Kalender-Events klassifizieren → Event-Typ bestimmen, Status-Hinweise erkennen
- **Provider:** Konfigurierbar: Anthropic Claude, OpenAI, Groq (Standard: `groq/llama-3.3-70b-versatile`), Ollama
- **API-Key:** Fernet-verschlüsselt in `ai_settings.api_key_enc`
- **Batch-Verarbeitung:** `classify_batch_for_app()` in `ai/tasks.py`, BATCH_SIZE konfigurierbar
- **Fallback:** Bei `AINotConfigured` / `AIRateLimited` werden Events ohne KI-Zusammenfassung gespeichert

---

## 4. Statusübergänge

### 4.1 Main-Status Pipeline

Der Hauptstatus einer Bewerbung folgt dieser Pipeline (Reihenfolge entspricht `MAIN_PIPELINE` im Frontend und `PIPELINE_ORDER` im Backend):

```
prospecting → applied → hr → fb → waiting → negotiating → signed
                 │
                 └──────────────────────────────────────────► rejected
                 (von jedem Status aus möglich via abgesagt=True)
```

| Status | Bedeutung | Beschreibung |
|---|---|---|
| `prospecting` | Anbahnung | Stelle identifiziert, noch nicht beworben |
| `applied` | Beworben | Bewerbung eingereicht |
| `hr` | Gespräch HR/HH | Personalrunden (HR oder Headhunter) |
| `fb` | Gespräch FB | Fachabteilungs-Interviews |
| `waiting` | Warten auf Entscheidung | Finale Entscheidung ausstehend |
| `negotiating` | Angebotsverhandlung | Angebot vorhanden, Konditionen klären |
| `signed` | Unterschrift | Vertrag unterschrieben |
| `rejected` | Absage | Absage erhalten oder ausgesprochen |

**Wichtig:** `rejected` steht **nicht** in der Lifecycle-Pipeline. Die Lifecycle-Bar zeigt die 7 Hauptschritte + separate Absage-Node. Bei abgesagten Bewerbungen wird der zuletzt erreichte Schritt aus den Timeline-Events inferiert.

### 4.2 Sub-Status (nur bei `hr` und `fb`)

Innerhalb der Stages `hr` und `fb` gibt es optionale Sub-Stati:

```
1_scheduled → 1_done → 2_scheduled → 2_done → 3_scheduled → 3_done → ...
```

| Sub-Status | Bedeutung |
|---|---|
| `1_scheduled` | 1. Gespräch terminiert |
| `1_done` | 1. Gespräch geführt |
| `2_scheduled` | 2. Gespräch terminiert |
| `2_done` | 2. Gespräch geführt |
| `3_scheduled` – `5_done` | analog |

Beim Wechsel zu einem Status ohne Sub-Status (`applied`, `waiting`, etc.) wird `sub_status` automatisch auf `null` gesetzt.

### 4.3 `abgesagt`-Flag

- Wird bei `main_status = rejected` automatisch auf `true` gesetzt (und umgekehrt)
- Filtert Bewerbungen aus der Standardliste aus (`show_rejected=false`)
- Steuert die rote Absage-Node in der Lifecycle-Bar

### 4.4 Statuswechsel-Regeln (Backend `applications.py`)

```
PATCH /api/applications/{id}
  main_status → rejected    ⟹  abgesagt = True  (auto)
  main_status → ≠rejected   ⟹  abgesagt = False (auto, wenn nicht explizit gesetzt)
  main_status → ≠{hr, fb}  ⟹  sub_status = None (auto)
  Statuswechsel (main oder sub) ⟹  Event typ="status" wird automatisch angelegt
```

### 4.5 Excel-Import-Mapping

Beim Excel-Import (`Bewerbungen_Eugen_Gulinsky.xlsx`, Sheet "Tracking") werden die alten flachen Statuswerte auf das neue 2-Felder-Modell gemappt:

| Excel-Wert | main_status | sub_status |
|---|---|---|
| `00 Anbahnung` | `prospecting` | – |
| `01 beworben` | `applied` | – |
| `02 1. Gespräch HR/HH terminiert` | `hr` | `1_scheduled` |
| `03 1. Gespräch HR/HH geführt` | `hr` | `1_done` |
| `05 2. Interview geführt` | `hr` | `2_done` |
| `06 1. Gespräch FB terminiert` | `fb` | `1_scheduled` |
| `07 3. Interview geführt` | `fb` | `1_done` |
| `08 2. Gespräch FB terminiert` | `fb` | `2_scheduled` |
| `12 Warten auf finale Entscheidung` | `waiting` | – |
| Abgesagt-Spalte = `x` | `rejected` | – |

---

## 5. Workflows

### 5.1 Manuelle Bewerbung anlegen

```
1. User: POST /api/applications/ (firma, rolle, main_status, datum_bewerbung)
2. Backend: Application-Objekt in DB schreiben
3. Backend: Event typ="bewerbung" automatisch anlegen (datum = datum_bewerbung oder today)
4. Response: ApplicationRead mit id, events[], contacts[]
```

### 5.2 Statuswechsel

```
1. User: PATCH /api/applications/{id} {main_status: "hr", sub_status: "1_scheduled"}
2. Backend: Felder aktualisieren, letztes_update = today
3. Backend: abgesagt / sub_status-Cleansing anwenden (siehe 4.4)
4. Backend: Event typ="status" mit Label "Gespräch HR/HH – 1. Gespräch terminiert" anlegen
5. Response: ApplicationRead (inkl. neuem Event)
```

### 5.3 Targeted Sync (Pro-Bewerbung)

```
1. User öffnet App-Modal → klickt "Sync"
2. Frontend: POST /api/sync/targeted/{app_id}
3. Backend startet BackgroundTask:
   a. Gmail: query = "from:Firma OR to:Firma OR subject:Firma" + Rollenwörter (OR)
   b. iCloud Mail: IMAP SEARCH + BODY-Filter
   c. GCal: Events mit Firmenname in Titel/Beschreibung
   d. iCloud Cal: CalDAV VEVENT-Suche
   e. Calls: Bridge-Query nach verknüpften Telefonnummern
   f. LinkedIn: Scraper-Check auf Bewerbungsstatus
4. Pro gefundenem Item:
   a. is_synced()? → überspringen
   b. AI classify_batch_for_app() → event_type, suggested_status, notiz
   c. Confidence ≥ 80? → save_classified_event() direkt speichern
      Confidence < 80? → PendingMatch anlegen für manuelle Review
5. save_classified_event():
   a. Event in DB schreiben (source, typ, datum, notiz mit HH:MM-Präfix)
   b. Sender/Organizer: upsert_contact_from_sender()
      → parseaddr() für Name+Email
      → _extract_footer_info() für Telefon/Rolle aus Mail-Footer
      → INSERT OR IGNORE in contact_application
   c. Status-Vorschlag prüfen → Application ggf. aktualisieren
   d. mark_synced()
6. Frontend: GET /api/sync/targeted/{app_id}/progress (Polling bis done)
```

### 5.4 Kontakt-Upsert aus Sync

```
upsert_contact_from_sender(db, raw_sender, app_id, firma, is_hh, event_date, body):
1. parseaddr(raw_sender) → (name, email_addr)
2. email_addr in _SKIP_CONTACT_LOCALS? → return (noreply, automated)
3. Contact mit matching email suchen
   FOUND:  leere Felder auffüllen (firma, rolle, telefon, letzter_kontakt)
   NOT FOUND: neuen Contact anlegen (name, email, firma, typ)
4. db.execute("INSERT OR IGNORE INTO contact_application VALUES (:cid, :aid)")
   [Direkt-SQL statt ORM-append, um SQLAlchemy-autoflush-Race zu vermeiden]
5. Wenn body vorhanden: _extract_footer_info(body, sender_name)
   → Regex für Telefon: "Tel.:", "Mobile:", "+49...", "0[0-9]{4,}"
   → Regex für Rolle: Label-Keywords nahe Sendername
   → Felder nur schreiben, wenn bisher leer
```

### 5.5 Excel-Import

```
1. POST /api/import/excel (multipart, Datei Bewerbungen_Eugen_Gulinsky.xlsx)
2. openpyxl Sheet "Tracking" lesen (ab Zeile 2)
3. Pro Zeile:
   a. EXCEL_IMPORT_MAP[status] → (main_status, sub_status)
   b. Abgesagt-Spalte = "x" → main_status = "rejected", abgesagt = True
   c. Application anlegen/aktualisieren
   d. Gespräch-Spalten 13–17 als Events typ="gespräch"
4. ImportResult {imported, skipped, errors}
```

### 5.6 Excel-Export

```
1. GET /api/export/excel[?show_rejected=true]
2. Alle Applications aus DB laden
3. EXCEL_EXPORT_MAP[(main_status, sub_status)] → Excel-Statuswert
4. openpyxl Workbook, Sheet "Tracking", 17 Spalten + Header
5. StreamingResponse application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
6. Dateiname: jobtracker_export_YYYY-MM-DD.xlsx
```

### 5.7 Review-Queue

```
Items mit Confidence < 80 landen in pending_matches:
1. GET /api/review/pending → Liste offener Matches mit Kontext
2. User bestätigt: POST /api/review/{id}/approve {application_id, event_type, datum, titel}
   → Event anlegen oder Status aktualisieren
   → review_status = "approved"
3. User verwirft: POST /api/review/{id}/reject
   → review_status = "rejected"
   → mark_synced() damit Item nicht erneut erscheint
```

---

## 6. Datenmodell

### Entity-Relationship-Übersicht

```
Application  1──*  Event
Application  *──*  Contact        (via contact_application)
Application  0──*  PendingMatch

GoogleSync          (singleton, Google OAuth Tokens)
ICloudSync          (singleton, iCloud Credentials)
LinkedInSync        (singleton, LinkedIn Credentials)
CallsConfig         (singleton, Calls-Bridge-Config)
AiSettings          (singleton, AI-Provider-Konfiguration)
SyncedItem          (Dedup-Log über alle Quellen)
```

### Tabellen im Detail

#### `applications`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | Auto-Increment |
| `firma` | VARCHAR NOT NULL | Firmenname |
| `rolle` | VARCHAR NOT NULL | Stellenbezeichnung |
| `main_status` | VARCHAR NOT NULL | Enum: `prospecting`…`rejected` |
| `sub_status` | VARCHAR NULL | `1_scheduled`…`5_done` (nur hr/fb) |
| `is_headhunter` | BOOLEAN | Wurde über Headhunter vermittelt |
| `zielfirma_bei_hh` | VARCHAR NULL | Zielfirma wenn HH = true |
| `quelle` | VARCHAR NULL | Herkunft (LinkedIn, XING, etc.) |
| `wurde_besetzt_von` | VARCHAR NULL | HH-Name wenn besetzt |
| `datum_bewerbung` | DATE NULL | Datum der Bewerbungsabgabe |
| `letztes_update` | DATE NULL | Letztes manuelles Update (überschrieben durch max(event.datum) bei Abfrage) |
| `abgesagt` | BOOLEAN | true → aus Standardliste gefiltert |
| `ghosting` | BOOLEAN | Keine Rückmeldung |
| `kommentar` | TEXT NULL | Freitext |
| `gespraech_1`…`5` | TEXT NULL | Notizen zu Gesprächen (aus Excel-Import) |
| `created_at` | DATETIME | Server-Timestamp bei Anlage |
| `updated_at` | DATETIME | Server-Timestamp bei Update |

> **Hinweis `letztes_update`:** Der gespeicherte Wert ist das letzte manuelle Update. Im `GET /api/applications/`-Endpoint wird `letztes_update` in-memory überschrieben durch `max(events.datum)`, falls dieser größer ist. Der Wert wird **nicht** in die DB zurückgeschrieben (kein `commit()` im GET).

#### `events`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | |
| `application_id` | INTEGER FK | → `applications.id` |
| `typ` | VARCHAR | `bewerbung`, `status`, `gespräch`, `mail`, `calendar`, `call`, `notiz` |
| `datum` | DATE NULL | Datum des Ereignisses |
| `titel` | VARCHAR NULL | Kurztitel |
| `notiz` | TEXT NULL | Langtext / KI-Zusammenfassung (Mails: beginnt mit `HH:MM Uhr\n`) |
| `autor` | VARCHAR NULL | Absender bei Mail-Events |
| `source` | VARCHAR NULL | `gmail`, `gcal`, `icloud_mail`, `icloud_cal`, `calls`, `linkedin` |
| `created_at` | DATETIME | |

#### `contacts`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | VARCHAR NOT NULL | Vollständiger Name |
| `email` | VARCHAR NULL | E-Mail-Adresse (für Dedup genutzt) |
| `telefon` | VARCHAR NULL | Telefonnummer (aus Footer-Extraktion) |
| `linkedin_url` | VARCHAR NULL | LinkedIn-Profil-URL |
| `foto_url` | VARCHAR NULL | Profilbild-URL |
| `firma` | VARCHAR NULL | Arbeitgeber |
| `rolle` | VARCHAR NULL | Position (aus Footer-Extraktion) |
| `typ` | VARCHAR NULL | `hr`, `hh`, `fb`, `other` |
| `notizen` | TEXT NULL | Freitext |
| `letzter_kontakt` | DATE NULL | Datum des letzten Events mit diesem Kontakt |
| `created_at` | DATETIME | |

#### `contact_application` (Join-Tabelle)

| Spalte | Typ | Beschreibung |
|---|---|---|
| `contact_id` | INTEGER PK/FK | → `contacts.id` ON DELETE CASCADE |
| `application_id` | INTEGER PK/FK | → `applications.id` ON DELETE CASCADE |

> **Hinweis:** Inserts erfolgen via `INSERT OR IGNORE` (Raw-SQL), nicht über ORM-`append()`, um SQLAlchemy-autoflush-Races bei doppelten Inserts in derselben Session zu vermeiden.

#### `synced_items`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | |
| `source` | VARCHAR NOT NULL | `gmail`, `gcal`, `icloud_mail`, `icloud_cal`, `calls`, `linkedin` |
| `external_id` | VARCHAR NOT NULL | Message-ID / Event-UID / MD5-Hash |
| `processed_at` | DATETIME | |

Dedup-Check: `SELECT 1 FROM synced_items WHERE source=? AND external_id=?`

#### `pending_matches`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | |
| `source` | VARCHAR | Sync-Quelle |
| `external_id` | VARCHAR | Für späteres mark_synced() |
| `confidence` | INTEGER | 0–100 (AI-Konfidenz) |
| `event_type` | VARCHAR NULL | Vom AI vorgeschlagener Event-Typ |
| `datum` | DATE NULL | |
| `titel` | VARCHAR NULL | |
| `extract` | TEXT NULL | Kurz-Snippet für Review-UI |
| `raw_content` | TEXT NULL | Vollständiger Original-Inhalt |
| `suggested_app_id` | INTEGER FK NULL | Vorgeschlagene Bewerbung |
| `suggested_main_status` | VARCHAR NULL | Vorgeschlagener neuer Status |
| `suggested_sub_status` | VARCHAR NULL | |
| `status_only` | BOOLEAN | True = nur Statuswechsel, kein neues Event |
| `review_status` | VARCHAR | `pending`, `approved`, `rejected` |
| `created_at` | DATETIME | |

#### `google_sync` (Singleton)

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | INTEGER PK | |
| `client_id` | VARCHAR | Google OAuth Client-ID |
| `client_secret_enc` | TEXT | Fernet-verschlüsselt |
| `access_token_enc` | TEXT NULL | Fernet-verschlüsselt |
| `refresh_token_enc` | TEXT NULL | Fernet-verschlüsselt |
| `token_expiry` | DATETIME NULL | |
| `oauth_state` | VARCHAR NULL | CSRF-Token während OAuth-Flow |
| `gmail_last_sync` | DATETIME NULL | Letzter erfolgreicher Gmail-Sync |
| `gcal_last_sync` | DATETIME NULL | Letzter erfolgreicher GCal-Sync |

#### `icloud_sync` (Singleton)

| Spalte | Typ | Beschreibung |
|---|---|---|
| `apple_id` | VARCHAR | Apple-ID (generische E-Mail) |
| `icloud_email` | VARCHAR NULL | `@icloud.com`/`@me.com` für IMAP |
| `app_password_enc` | TEXT | Fernet-verschlüsselt (App-Specific Password) |
| `web_password_enc` | TEXT NULL | Apple-ID-Passwort für pyicloud |
| `mail_last_sync` | DATETIME NULL | |
| `calendar_last_sync` | DATETIME NULL | |
| `contacts_last_sync` | DATETIME NULL | |

#### `ai_settings` (Singleton)

| Spalte | Typ | Beschreibung |
|---|---|---|
| `provider` | VARCHAR | `groq`, `anthropic`, `openai`, `ollama` |
| `model` | VARCHAR | z.B. `groq/llama-3.3-70b-versatile` |
| `api_key_enc` | TEXT NULL | Fernet-verschlüsselt; NULL bei Ollama |
| `base_url` | VARCHAR NULL | Für Ollama / Custom-Endpoints |
| `enabled` | BOOLEAN | AI-Klassifikation aktiv |

#### `linkedin_sync` (Singleton)

| Spalte | Typ | Beschreibung |
|---|---|---|
| `email` | VARCHAR | LinkedIn-Account |
| `password_enc` | TEXT | Fernet-verschlüsselt |
| `session_cookies` | TEXT NULL | JSON-Blob (gecachte Login-Cookies) |
| `last_sync` | DATETIME NULL | |

#### `calls_config` (Singleton)

| Spalte | Typ | Beschreibung |
|---|---|---|
| `enabled` | BOOLEAN | Bridge aktiv |
| `last_sync` | DATETIME NULL | |

### Kryptographie

Alle sensitiven Felder (Passwörter, OAuth-Tokens, API-Keys) werden mit **Fernet** (symmetrische AEAD-Verschlüsselung aus der `cryptography`-Bibliothek) verschlüsselt. Der Schlüssel wird aus einem applikationsinternen Secret abgeleitet und niemals in der Datenbank gespeichert.

Functions in `app/ai/provider.py`:
- `encrypt_api_key(plaintext: str) -> str` — verschlüsselt und gibt Base64-String zurück
- `decrypt_api_key(ciphertext: str) -> str` — entschlüsselt

---

## CI/CD (GitHub Actions)

Datei: `.github/workflows/ci.yml`

| Job | Trigger | Schritte |
|---|---|---|
| `backend` | Push/PR auf `main` | `ruff check` (E,F,W), `pyright` (informational) |
| `frontend` | Push/PR auf `main` | `tsc --noEmit`, `vite build` |
| `docker` | Push auf `main` (nach backend+frontend) | Docker Buildx für beide Images (kein Push) |

Repository: [github.com/EGulinsky/jobtracker](https://github.com/EGulinsky/jobtracker) (privat)
