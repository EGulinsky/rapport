# JobTracker MVP

Self-hosted Bewerbungs-Tracking App als Ersatz für die Excel-Liste.

## Voraussetzungen

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac / Linux / Windows)
- Die Excel-Datei `Bewerbungen_Eugen_Gulinsky.xlsx` zum Import

## Schnellstart

```bash
# 1. In den Projektordner wechseln
cd jobtracker

# 2. App starten (erstmaliger Build dauert ~2 Minuten)
docker compose up -d --build

# 3. Browser öffnen
open http://localhost:3000
```

## Excel-Daten importieren

1. App im Browser öffnen: http://localhost:3000
2. Oben rechts auf **„Excel importieren"** klicken
3. `Bewerbungen_Eugen_Gulinsky.xlsx` auswählen
4. Alle 133 Einträge werden automatisch importiert

## Funktionen (MVP)

| Feature | Beschreibung |
|---|---|
| **Dashboard** | Tabellenansicht aller Bewerbungen, sortierbar nach Firma / Status / Datum |
| **Kanban-Board** | Pipeline-Ansicht nach Bewerbungsstatus |
| **Filter** | Nach Status filtern, Abgesagte ein-/ausblenden, Freitextsuche |
| **Detailansicht** | Vollständiges Profil inkl. Gesprächsnotizen, Bearbeiten / Löschen |
| **Neue Bewerbung** | Direkt aus der App anlegen |
| **Excel Import** | Bestehende `.xlsx` per Drag & Drop oder Datei-Auswahl importieren |
| **KPI-Kacheln** | Gesamt / Aktiv / Abgesagt / Interview-Rate auf einen Blick |

## API-Dokumentation

Swagger UI: http://localhost:8000/docs

## App stoppen

```bash
docker compose down
```

Daten bleiben erhalten (Docker Volume `jobtracker-data`).

## Entwicklungsmodus (ohne Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (neues Terminal)
cd frontend
npm install
npm run dev
```

---

**Nächste Schritte (Phase 2):** LinkedIn Sync · Gmail Integration · Google Calendar · Kontakt-CRM
