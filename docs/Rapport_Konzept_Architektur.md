# rapport – Konzept & Software-Architektur

**Version:** 1.0 · **Datum:** 10. Juni 2026  
**Ziel:** Selbst-gehostete Web-App als Ersatz für die Excel-Bewerbungsliste

> **Hinweis:** Dies ist das ursprüngliche Planungsdokument. Einige Entscheidungen wurden in der Implementierung abgeändert (z. B. SQLite statt PostgreSQL, kein Celery/Redis). Den aktuellen Ist-Stand beschreibt [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Produktvision

rapport ist eine schlanke, selbst-gehostete Webanwendung, die den gesamten Bewerbungsprozess von der ersten Kontaktaufnahme bis zur Zu- oder Absage abbildet. Sie zieht Daten automatisch aus LinkedIn, Gmail und Google Calendar, reichert Firmenprofile mit öffentlichen Quellen an und liefert KPI-Dashboards sowie KI-basierte Handlungsempfehlungen.

**Kernprinzipien:**
- Self-hosted: Daten bleiben lokal / auf eigenem Server
- Automatisierung wo sinnvoll, manuelle Kontrolle wo nötig
- Import der bestehenden Excel als Startdatenpunkt
- Keine Vendor-Lock-in: offene Standards (REST, OAuth, Docker)

---

## 2. Hauptfunktionen

### 2.1 Dashboard & Pipeline-Ansicht
- Kanban-Board oder Tabellenansicht aller laufenden Bewerbungen
- Status-Swimlanes: Beworben → 1. Gespräch → 2. Gespräch → Angebot → Abgesagt
- Farbkodierung nach Dringlichkeit / Inaktivität (z. B. rot = kein Update seit > 14 Tagen)
- Filtermöglichkeiten: Headhunter / Direktbewerbung, Quelle, Zeitraum

### 2.2 Next Steps & Erinnerungen
- Pro Bewerbung: offene Aufgaben mit Fälligkeitsdatum (z. B. „Follow-up senden", „Dankes-Mail nach Interview")
- Automatische Vorschläge auf Basis des Status (nach 7 Tagen ohne Antwort → Reminder)
- Sync mit Google Calendar: Interviews und Deadlines erscheinen im Kalender
- E-Mail-Benachrichtigungen (optional Push über Browser)

### 2.3 Firmen- & Kontaktprofile
- Automatisch befüllte Profile: Logo, Branche, Größe, LinkedIn-URL, Glassdoor-Rating
- Datenquellen: Clearbit, LinkedIn Company API, eigene Web-Suche
- Gesprächspartner mit Name, Rolle, LinkedIn-Profil, E-Mail
- Notizen-Bereich pro Firma und pro Person

### 2.4 Analytics & KPIs
- Bewerbungsrate pro Woche / Monat
- Conversion-Funnel: Beworben → Interview → 2. Runde → Angebot
- Antwortzeiten-Analyse (Tage bis Rückmeldung)
- Quellen-Effektivität (LinkedIn Direct / XING / Headhunter / Firmen-Website)
- KI-Vorschläge: „Du bewirbst dich zu selten bei mittelgroßen Firmen" / „Headhunter-Kanäle liefern kaum Interviews"

### 2.5 Import & Export
- One-click Import der bestehenden Excel (`Bewerbungen_Eugen_Gulinsky.xlsx`)
- Export als Excel oder CSV jederzeit möglich
- Backup-Funktion (lokal oder Cloud-Speicher)

---

## 3. Tech-Stack

| Schicht | Technologie | Begründung |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | Schnell, async-fähig, gute Ökosystem-Reife |
| Task Queue | **Celery + Redis** | Geplante Syncs, asynchrone Hintergrundaufgaben |
| Datenbank | **PostgreSQL 16** | Robust, SQL, gut mit SQLAlchemy nutzbar |
| ORM | **SQLAlchemy 2 + Alembic** | Migrationen, typsichere Queries |
| Frontend | **React 18 + Vite + TypeScript** | Modernes SPA, gute Komponentenbibliotheken |
| UI-Bibliothek | **shadcn/ui + Tailwind CSS** | Sauberes Design, kein Overhead |
| Charts | **Recharts** | React-native, einfach anpassbar |
| Auth | **JWT + OAuth 2.0 (Google)** | Single-User mit Google-Login für API-Zugriff |
| KI-Layer | **Claude API (Haiku/Sonnet)** | Zusammenfassungen, Vorschläge, Profil-Enrichment |
| Deployment | **Docker Compose + Nginx** | Ein-Befehl-Start, HTTPS via Let's Encrypt |
| Hosting | **Raspberry Pi 5 oder VPS** | Self-hosted, monatlich < 5 € |

---

## 4. Datenmodell (vereinfacht)

```
Application
  ├── id, firma, rolle, quelle, hh_flag
  ├── datum_bewerbung, letztes_update
  ├── status (enum: applied | phone_screen | interview_1 | interview_2 | offer | rejected)
  ├── abgesagt_flag, ghosting_flag
  ├── company_id → Company
  └── events[] → Event

Company
  ├── id, name, linkedin_url, website
  ├── branche, mitarbeiterzahl, glassdoor_rating
  ├── logo_url, beschreibung
  └── contacts[] → Contact

Contact                                   ← CRM-Kernentität
  ├── IDENTITÄT
  │   ├── id, name, foto_url
  │   ├── email[] (work + privat)
  │   ├── telefon[] (mobil, büro)
  │   ├── linkedin_url, xing_url
  ├── BERUFLICHER KONTEXT
  │   ├── company_id → Company
  │   ├── rolle, abteilung
  │   ├── typ: HR | Headhunter | Fachbereich | CEO | Sonstige
  │   ├── entscheidungsträger (bool)
  │   └── seniority: Junior | Senior | C-Level
  ├── BEZIEHUNG
  │   ├── erstkontakt_datum, letzter_kontakt (auto-berechnet)
  │   ├── kanal: Mail | LinkedIn | Telefon | Persönlich
  │   ├── wärme: Kalt | Warm | Netzwerk
  │   ├── applications[] → Applications
  │   └── tags[] (frei vergebbar)
  ├── KOMMUNIKATIONSHISTORIE
  │   └── interactions[]
  │       ├── typ: Mail | Anruf | Meeting | LinkedIn-Msg | Videocall
  │       ├── datum, betreff, notiz
  │       ├── gmail_thread_id (verknüpft mit Gmail)
  │       └── cal_event_id (verknüpft mit Google Calendar)
  ├── IMPORT-QUELLEN (Dedup-Keys)
  │   ├── linkedin_id
  │   ├── gmail_contact_id
  │   ├── vcard_uid (aus Telefonliste / vCard-Import)
  │   └── enrichment_confidence (0–1), auto_enriched_at
  └── KI & NOTIZEN
      ├── persoenliche_notizen (Freitext, nach Gespräch)
      ├── ki_zusammenfassung (auto-generiert)
      ├── followup_empfehlung (KI)
      └── reminders[] → Reminder

Event
  ├── id, application_id, typ (interview | email | phone | note)
  ├── datum, notiz, google_calendar_event_id
  └── next_step (text, due_date)

Reminder
  ├── id, application_id oder contact_id, text, due_date
  ├── kanal (email | push | calendar)
  └── erledigt_flag
```

---

## 5. Integrations-Architektur

### LinkedIn
- **Kurzfristig:** Weiterführung des bestehenden Browser-Scraping via Claude in Chrome (kein offizieller API-Zugang für private Nutzer)
- **Mittelfristig:** Playwright-basierter Headless-Scraper als Celery-Task (täglich oder manuell angestoßen)
- Mapping LinkedIn-Status → interne Status-Enum

### Gmail
- Google OAuth 2.0 für Lesezugriff
- Suche nach Bewerbungs-relevanten Mails (Filter: „Absage", „Interview", „Termin", „Einladung")
- Automatische Verlinkung Mail ↔ Bewerbung über Firma/Rolle im Betreff
- Anhänge (Stellenausschreibungen) optional speichern

### Google Calendar
- Lese- und Schreibzugriff via Google Calendar API
- Interviews + Follow-up-Dates automatisch als Events anlegen
- Zwei-Wege-Sync: Änderungen im Kalender reflektieren sich in der App

### Firmenprofile (Web Research)
- Clearbit Company API (kostenlos bis 2.500 Anfragen/Monat)
- Fallback: eigene Web-Suche (DuckDuckGo API oder SerpAPI)
- LinkedIn Company Scraping für Logo + Mitarbeiterzahl
- Cache in PostgreSQL (kein Wiederabruf innerhalb von 30 Tagen)

---

## 5b. Kontakt-Management (CRM-Modul) – Detail

### Datenquellen & Enrichment-Flow

Jeder Kontakteintrag wird automatisch aus mehreren Quellen zusammengeführt:

1. **vCard / CSV-Import** (Telefonliste): Name + Telefonnummer als Basis
2. **Gmail Signatur-Parser**: Celery-Task parst Signaturen eingehender Mails → extrahiert Rolle, Firma, E-Mail, Telefon
3. **LinkedIn Scraper**: Foto, aktueller Titel, Karrierehistorie
4. **Google Calendar**: Termine mit dem Kontakt werden automatisch als Interactions verlinkt
5. **Manuell**: Persönliche Notizen, Eindrücke nach Gesprächen, Tags

Dedup-Logik: Zusammenführung über `email` (primär), `linkedin_id`, `vcard_uid` — verhindert doppelte Einträge wenn dieselbe Person aus mehreren Quellen kommt.

### Kontakttypen & Rollen

- **HR / Recruiting** – Erstkontakt, koordiniert Prozess
- **Headhunter** – externer Vermittler (wird mit HH-Firma verknüpft, nicht Zielfirma)
- **Fachbereich (FB)** – zukünftiger Vorgesetzter / Kollege im Interview
- **C-Level** – Entscheidungsträger (CEO, CTO, etc.)
- **Netzwerk** – kein aktiver Bewerbungskontext, aber relevant halten

### KI-Funktionen pro Kontakt

- **Gesprächszusammenfassung**: Claude fasst Meeting-Notizen in 2–3 Sätzen zusammen
- **Follow-up Empfehlung**: „Noch keine Antwort nach 14 Tagen → freundliche Nachfass-Mail"
- **Gemeinsame Themen erkennen**: Aus Mailhistorie extrahierte Interessen / Schwerpunkte
- **Beziehungsstärke-Score**: Berechnet aus Kontakthäufigkeit, Reaktionszeit, Gesprächstiefe

### Ansichten im Frontend

- **Kontaktliste**: Filterbar nach Typ, Firma, Wärme, letztem Kontakt
- **Kontaktdetail**: Timeline aller Interaktionen (Mails, Anrufe, Meetings), verknüpfte Bewerbungen, KI-Zusammenfassung
- **Netzwerk-Karte**: Visuelle Darstellung: Kontakt ↔ Firma ↔ Bewerbung
- **Follow-up Queue**: Wer braucht heute / diese Woche eine Reaktion?

---

## 6. Frontend-Module

```
/dashboard        → Kanban + Tabellenansicht, Quick-Actions
/applications/:id → Detailseite: Timeline, Kontakte, Notizen, Next Steps
/contacts         → CRM-Kontaktliste, Filterbar, Follow-up Queue
/contacts/:id     → Kontaktdetail: Profil, Interaktionsverlauf, KI-Insights
/companies/:id    → Firmenprofil + alle Bewerbungen + Kontakte bei dieser Firma
/analytics        → KPI-Charts, Funnel-Analyse, KI-Insights
/calendar         → Agenda-Ansicht, Google Cal Sync-Status
/settings         → OAuth-Verbindungen, Sync-Intervalle, Benachrichtigungen
/import           → Excel-Upload + vCard-Import + Mapping-Assistent
```

---

## 7. Deployment

```yaml
# docker-compose.yml (vereinfacht)
services:
  app:       # FastAPI Backend (Port 8000)
  frontend:  # React Build (nginx, Port 3000)
  db:        # PostgreSQL
  redis:     # Celery Broker
  celery:    # Background Worker
  nginx:     # Reverse Proxy (Port 443, HTTPS)
```

**Start:** `docker compose up -d`  
**Zugriff:** `https://jobs.local` oder eigene Domain  
**Backup:** täglicher PostgreSQL-Dump als Cronjob, optional zu Google Drive

---

## 8. Entwicklungs-Roadmap

| Phase | Inhalt | Aufwand |
|---|---|---|
| **Phase 1 – MVP** | Excel-Import, CRUD für Bewerbungen, einfaches Dashboard | ~3–4 Wochen |
| **Phase 2 – Sync** | LinkedIn-Scraper, Gmail-Integration, Reminder-System | ~2–3 Wochen |
| **Phase 3 – Enrichment** | Google Calendar, Firmenprofile, Kontakte | ~2 Wochen |
| **Phase 4 – Analytics** | KPI-Charts, KI-Insights (Claude API), Funnel-Analyse | ~2 Wochen |
| **Phase 5 – Polish** | Mobile-optimiertes UI, Notifications, Backup-Automatisierung | ~1 Woche |

**Gesamtaufwand (Nebenprojekt):** ca. 10–12 Wochen bei ca. 5–8h/Woche

---

## 9. Nächste Schritte

1. **Entscheidung:** Raspberry Pi oder VPS als Hosting-Plattform?
2. **Repo anlegen:** GitHub-Repository mit Projektstruktur scaffolden
3. **Phase 1 starten:** FastAPI-Projekt + React-Vite-Skeleton + Docker Compose aufsetzen
4. **Excel importieren:** Bestehende 133 Einträge als initiale Daten laden

---

*Dieses Dokument ist das ursprüngliche Planungskonzept vom 10. Juni 2026 und wird bewusst nicht mehr aktualisiert — es dient als Ausgangspunkt-Referenz. Der aktuelle Stand wird in [ARCHITECTURE.md](ARCHITECTURE.md) gepflegt.*
