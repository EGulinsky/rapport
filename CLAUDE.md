# JobTracker – Claude Code Kontext

Self-hosted Bewerbungs-Tracking-App als Ersatz für `Bewerbungen_Eugen_Gulinsky.xlsx`.

## Projekt starten

```bash
# App starten (OrbStack / Docker muss laufen)
docker compose up -d

# Frontend-Entwicklung (lokal, ohne Docker)
cd frontend && npm install && npm run dev   # http://localhost:3000

# Backend-Entwicklung (lokal, ohne Docker)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload              # http://localhost:8000
```

## Projektstruktur

```
jobtracker/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI App + CORS + Lifespan
│   │   ├── database.py      # SQLAlchemy + SQLite Setup
│   │   ├── models.py        # ORM-Modelle + Status-Enum + Excel-Mapping
│   │   ├── schemas.py       # Pydantic-Schemas (Request/Response)
│   │   └── routers/
│   │       ├── applications.py   # CRUD + Events + Contacts
│   │       └── import_excel.py   # POST /api/import/excel
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx               # Hauptkomponente: Dashboard + Filter + Kanban
│       ├── types.ts              # TypeScript-Typen + Status-Labels/Farben
│       ├── api/client.ts         # Fetch-Wrapper für alle API-Calls
│       └── components/
│           ├── ApplicationTable.tsx   # Sortierbare Tabelle
│           ├── ApplicationModal.tsx   # Detail/Edit-Modal
│           ├── StatsBar.tsx           # KPI-Kacheln oben
│           ├── StatusBadge.tsx        # Farbige Status-Badges
│           └── ImportButton.tsx       # Excel-Upload-Button
└── docker-compose.yml
```

## Datenbank

SQLite unter `backend/data/jobtracker.db` (Docker Volume `jobtracker-data`).
Schema wird beim Start automatisch via SQLAlchemy `create_all()` erstellt — kein Alembic nötig für MVP.

## Status-Mapping (Excel → App)

| Excel-Wert | Interner Status |
|---|---|
| `00 Anbahnung` | `prospecting` |
| `01 beworben` | `applied` |
| `02 1. Gespräch HR/HH terminiert` | `hr_scheduled` |
| `03 1. Gespräch HR/HH geführt` | `hr_done` |
| `05 2. Interview geführt` | `interview_2` |
| `06 1. Gespräch FB terminiert` | `fb_scheduled` |
| `07 3. Interview geführt` | `interview_3` |
| `08 2. Gespräch FB terminiert` | `fb_2` |
| `12 Warten auf finale Entscheidung` | `final_decision` |
| Abgesagt-Flag = x | `rejected` |

## API-Endpunkte

```
GET    /api/applications/          Liste (filter: status, search, show_rejected)
GET    /api/applications/stats     KPI-Zahlen
GET    /api/applications/{id}      Detail mit Events + Contacts
POST   /api/applications/          Neu anlegen
PATCH  /api/applications/{id}      Aktualisieren
DELETE /api/applications/{id}      Löschen
POST   /api/applications/{id}/events    Event hinzufügen
POST   /api/applications/{id}/contacts  Kontakt hinzufügen
POST   /api/import/excel           Excel-Import (multipart/form-data)
GET    /health                     Health-Check
```

Swagger UI: http://localhost:8000/docs

## Was bereits gebaut ist (MVP)

- [x] FastAPI Backend mit SQLite
- [x] Alle CRUD-Endpunkte für Bewerbungen
- [x] Excel-Import (liest `Bewerbungen_Eugen_Gulinsky.xlsx`, 133 Einträge)
- [x] React Frontend mit Tailwind CSS
- [x] Tabellenansicht (sortierbar nach Firma/Status/Datum)
- [x] Kanban-Board nach Status-Spalten
- [x] Status-Filter-Tabs mit Live-Zähler
- [x] Detail/Edit-Modal mit allen Feldern
- [x] KPI-Kacheln (Gesamt / Aktiv / Abgesagt / Interview-Rate)
- [x] Docker Compose + OrbStack-kompatibel

## Phase 2 – Nächste Features

### Kontakt-Management (CRM)
- Vollständige Kontaktdetailseite (`/contacts/:id`) mit Interaktions-Timeline
- vCard / CSV Import für Telefonliste
- Gmail-Signatur-Parser (Rolle + Firma + Tel automatisch extrahieren)
- KI-Zusammenfassung pro Kontakt (Claude API)

### LinkedIn-Sync
- Playwright-basierter Scraper als Celery-Task
- Mapping LinkedIn-Status → interne Status-Enum
- Täglich oder manuell angestoßen

### Gmail-Integration
- Google OAuth 2.0 (nur Lesezugriff)
- Bewerbungsrelevante Mails automatisch erkennen und verknüpfen
- Endpoint: `GET /api/integrations/gmail/sync`

### Google Calendar
- Interview-Termine automatisch als Events anlegen
- Zwei-Wege-Sync
- Endpoint: `POST /api/integrations/calendar/sync`

### Analytics
- KPI-Funnel-Chart (Recharts)
- Quellen-Effektivität (LinkedIn / XING / Headhunter)
- Antwortzeiten-Analyse
- Claude API für KI-Insights

## Wichtige Entscheidungen

- **SQLite statt PostgreSQL**: Für Single-User reicht SQLite, kein separater DB-Container nötig
- **Kein Alembic für MVP**: `create_all()` beim Start, Migrationen erst wenn Schema stabilisiert
- **CORS offen**: `allow_origins=["*"]` für MVP, vor Produktiv-Einsatz einschränken
- **Kein Auth für MVP**: Single-User lokal, Auth (JWT + Google OAuth) kommt in Phase 3

## Excel-Datei

Original liegt unter:
`/Users/eugengulinsky/Documents/Bewerbungen und Arbeitsverträge/Ich/Aktuell/Stellen/Bewerbungen_Eugen_Gulinsky.xlsx`

Sheet: `Tracking`, 17 Spalten:
Firma(1) | HH?(2) | Zielfirma(3) | Rolle(4) | BesetztvonHH(5) | Quelle(6) |
DatumBewerbung(7) | LetztesUpdate(8) | Status(9) | Ghosting(10) | Abgesagt(11) |
Kommentar(12) | Gespräch1–5(13–17)
