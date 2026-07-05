<p align="center">
  <img src="frontend/public/brand/logo.svg" alt="rapport" width="220" />
</p>

# rapport

Self-hosted CRM für deine Bewerbungssuche — Ersatz für die Excel-Bewerbungsliste.  
Läuft lokal in OrbStack / Docker Compose. Aktueller Stand: siehe In-App-Changelog (Version in `frontend/src/components/ChangelogModal.tsx`).

Technische Architektur mit Diagrammen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Voraussetzungen

- [OrbStack](https://orbstack.dev/) oder Docker Desktop (Mac / Linux / Windows)

## Schnellstart

```bash
# 1. In den Projektordner wechseln
cd /Users/eugengulinsky/code/jobtracker

# 2. App starten (erstmaliger Build dauert ~2–3 Minuten)
docker compose up -d --build

# 3. Browser öffnen
open http://192.168.117.10        # OrbStack (empfohlen, kein Proxy-Cache)
# oder: open http://localhost:3000
```

## Funktionen

| Feature | Beschreibung |
|---|---|
| **Dashboard / Tabelle** | Alle Bewerbungen, sortierbar; „Nächster Schritt" intelligent berechnet |
| **Kanban-Board** | Pipeline-Ansicht mit Drag & Drop nach Status-Spalten |
| **Kalender-Ansicht** | Outlook-ähnlich: Tag / Arbeitswoche / Woche / Monat |
| **Filter & Suche** | Nach Status, Freitext, Abgesagte ein-/ausblenden |
| **Detail-Modal** | Vollständiges Profil, Lifecycle-Bar, Timeline, Gesprächsnotizen |
| **Kontakte (CRM)** | Kontaktpersonen mit n:m-Verknüpfung zu Bewerbungen |
| **Excel Import** | `.xlsx` im Originalformat (Sheet „Tracking", 17 Spalten) |
| **Excel Export** | Rückexport ins gleiche Format |
| **KPI-Kacheln** | Gesamt / Aktiv / Abgesagt / Interview-Rate |
| **LinkedIn Sync** | Playwright-Scraper: Archived → abgesagt, Status-Updates |
| **Gmail Sync** | Google OAuth 2.0, bewerbungsrelevante Mails verknüpfen |
| **Google Calendar** | Interview-Termine als Events, Kontakte aus Teilnehmerliste |
| **iCloud Mail** | IMAP-Sync (App-Specific Password) |
| **iCloud Kalender** | CalDAV-Sync |
| **iCloud Kontakte** | CardDAV-Import |
| **Lokale Dokumente** | PDF/DOCX/TXT/MD über den JobTracker Agent |
| **Review-Queue** | KI-Vorschläge für Events und Statuswechsel freigeben |
| **Sync-Steuerung** | Quellen einzeln aktivieren / deaktivieren |
| **AI-Klassifikation** | Provider-agnostisch via LiteLLM (Groq, Ollama, OpenAI, Anthropic) |
| **KI-Erfolgsbewertung** | Ampel (grün/gelb/rot) je Bewerbung inkl. Begründung + nächstem Schritt; bei Absagen Absagegrund-Analyse |
| **LinkedIn-Import** | Stellenanzeigen-Link einfügen → Firma/Rolle/Quelle automatisch per KI extrahiert |
| **Firmenprofile** | Eigene Firmenansicht mit Logo, Branche, Standort, Mitarbeiterzahl (automatisch angereichert) |
| **Zusammenführen** | Duplikate bei Bewerbungen, Kontakten und Firmen manuell oder automatisch mergen |
| **Bereinigen** | Kontextsensitive Dublettenerkennung (Bewerbungen/Kontakte/Firmen/Kalender) |
| **Dateianhänge** | Anhänge aus Sync-Quellen an Timeline-Events, herunterladbar |
| **PDF-Export** | Export der Eigenbemühungen als PDF |
| **Auswertungen** | Pipeline-Funnel und Absage-Statistiken |
| **Audit-Log** | Nachvollziehbare Änderungshistorie je Bewerbung |
| **Backup** | Konfigurierbare lokale Datenbank-Backups |
| **Changelog** | Versionsverlauf im App-Header abrufbar |

## Einstellungen

### LinkedIn
1. Einstellungen → LinkedIn → E-Mail + Passwort eintragen
2. „Sync starten" — bei 2FA: Push-Notification bestätigen **oder** Code eingeben

### Google (Gmail + Calendar)
1. Google Cloud Console → OAuth 2.0 Client (Web), Redirect URI: `http://localhost:8000/api/sync/google/callback`
2. Einstellungen → Google: Client ID + Secret eintragen → OAuth-Flow starten

### iCloud (Mail + Kalender + Kontakte)
1. Apple ID → Sicherheit → App-spezifische Passwörter → neues Passwort generieren
2. Einstellungen → iCloud: Apple-ID + App-Passwort eintragen

### Lokale Dokumente (+ Notizen, Anrufe, Backup)
Erfordert den JobTracker Agent auf dem Mac (siehe [agent/README.md](agent/README.md) — als `.app`/`.dmg` installierbar, läuft dauerhaft im Hintergrund mit Menüleisten-Icon, keine manuellen Terminal-Fenster mehr). Nach der Installation: Einstellungen → Agent → Token einfügen (wird beim ersten Start des Agenten in der Menüleiste angezeigt). Dann Einstellungen → Dokumente → Ordnerpfad setzen.

### AI-Provider
- **Groq** (empfohlen, kostenlos): API-Key von [console.groq.com](https://console.groq.com), Modell `groq/llama-3.3-70b-versatile`
- **Ollama** (lokal, kein API-Key): Base URL `http://host.docker.internal:11434`

## API-Dokumentation

Swagger UI: `http://localhost:8000/docs`

## Isolierte Testumgebung

Für gefahrloses Testen (z.B. Restore aus einem Produktiv-Backup) gibt es eine separate 1:1-Umgebung mit eigener, leerer Datenbank — komplett getrennt von den echten Daten und im Frontend deutlich mit einem roten "TESTUMGEBUNG"-Banner markiert.

```bash
docker compose -p jobtracker-test -f docker-compose.test.yml up -d --build
```

- GUI: `http://localhost:3001`
- API/Swagger: `http://localhost:8001/docs`

Zurücksetzen (löscht auch die Test-Datenbank):

```bash
docker compose -p jobtracker-test -f docker-compose.test.yml down -v
```

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
uvicorn app.main:app --reload    # http://localhost:8000

# Frontend (neues Terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

## Lizenz

[Business Source License 1.1](LICENSE) — freie Nutzung für private, nicht-kommerzielle Zwecke. Für eine kommerzielle Nutzung ist eine separate Lizenz erforderlich.
