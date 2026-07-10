# rapport – Concept & Software Architecture

**Version:** 1.0 · **Date:** June 10, 2026
**Goal:** Self-hosted web app as a replacement for the Excel application list

> **Note:** This is the original planning document. Some decisions were changed during implementation (e.g. SQLite instead of PostgreSQL, no Celery/Redis). The current actual state is described in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Product Vision

rapport is a lean, self-hosted web application that maps the entire application process from first contact to offer or rejection. It automatically pulls data from LinkedIn, Gmail, and Google Calendar, enriches company profiles with public sources, and delivers KPI dashboards as well as AI-based recommendations for action.

**Core principles:**
- Self-hosted: data stays local / on your own server
- Automation where it makes sense, manual control where needed
- Import of the existing Excel sheet as the starting data point
- No vendor lock-in: open standards (REST, OAuth, Docker)

---

## 2. Main Features

### 2.1 Dashboard & Pipeline View
- Kanban board or table view of all ongoing applications
- Status swimlanes: Applied → 1st interview → 2nd interview → Offer → Rejected
- Color coding by urgency / inactivity (e.g. red = no update in > 14 days)
- Filter options: headhunter / direct application, source, time period

### 2.2 Next Steps & Reminders
- Per application: open tasks with a due date (e.g. "send follow-up", "thank-you email after interview")
- Automatic suggestions based on status (7 days with no response → reminder)
- Sync with Google Calendar: interviews and deadlines appear in the calendar
- Email notifications (optional push via browser)

### 2.3 Company & Contact Profiles
- Automatically populated profiles: logo, industry, size, LinkedIn URL, Glassdoor rating
- Data sources: Clearbit, LinkedIn Company API, own web search
- Contact persons with name, role, LinkedIn profile, email
- Notes section per company and per person

### 2.4 Analytics & KPIs
- Application rate per week / month
- Conversion funnel: applied → interview → 2nd round → offer
- Response-time analysis (days until reply)
- Source effectiveness (LinkedIn direct / XING / headhunter / company website)
- AI suggestions: "You apply too rarely to mid-sized companies" / "Headhunter channels yield hardly any interviews"

### 2.5 Import & Export
- One-click import of the existing Excel file (`Bewerbungen_Eugen_Gulinsky.xlsx`)
- Export as Excel or CSV possible at any time
- Backup function (local or cloud storage)

---

## 3. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend | **Python 3.12 + FastAPI** | Fast, async-capable, mature ecosystem |
| Task queue | **Celery + Redis** | Scheduled syncs, asynchronous background tasks |
| Database | **PostgreSQL 16** | Robust, SQL, works well with SQLAlchemy |
| ORM | **SQLAlchemy 2 + Alembic** | Migrations, type-safe queries |
| Frontend | **React 18 + Vite + TypeScript** | Modern SPA, good component libraries |
| UI library | **shadcn/ui + Tailwind CSS** | Clean design, no overhead |
| Charts | **Recharts** | React-native, easy to customize |
| Auth | **JWT + OAuth 2.0 (Google)** | Single-user with Google login for API access |
| AI layer | **Claude API (Haiku/Sonnet)** | Summaries, suggestions, profile enrichment |
| Deployment | **Docker Compose + Nginx** | One-command start, HTTPS via Let's Encrypt |
| Hosting | **Raspberry Pi 5 or VPS** | Self-hosted, < €5/month |

---

## 4. Data Model (Simplified)

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

Contact                                   ← CRM core entity
  ├── IDENTITY
  │   ├── id, name, foto_url
  │   ├── email[] (work + personal)
  │   ├── telefon[] (mobile, office)
  │   ├── linkedin_url, xing_url
  ├── PROFESSIONAL CONTEXT
  │   ├── company_id → Company
  │   ├── rolle, abteilung
  │   ├── typ: HR | Headhunter | Fachbereich | CEO | Other
  │   ├── entscheidungsträger (bool, decision-maker)
  │   └── seniority: Junior | Senior | C-Level
  ├── RELATIONSHIP
  │   ├── erstkontakt_datum (first-contact date), letzter_kontakt (last contact, auto-computed)
  │   ├── kanal (channel): Mail | LinkedIn | Phone | In person
  │   ├── wärme (warmth): Cold | Warm | Network
  │   ├── applications[] → Applications
  │   └── tags[] (freely assignable)
  ├── COMMUNICATION HISTORY
  │   └── interactions[]
  │       ├── typ: Mail | Call | Meeting | LinkedIn message | Video call
  │       ├── datum, betreff, notiz (date, subject, note)
  │       ├── gmail_thread_id (linked to Gmail)
  │       └── cal_event_id (linked to Google Calendar)
  ├── IMPORT SOURCES (dedup keys)
  │   ├── linkedin_id
  │   ├── gmail_contact_id
  │   ├── vcard_uid (from phone contact list / vCard import)
  │   └── enrichment_confidence (0–1), auto_enriched_at
  └── AI & NOTES
      ├── persoenliche_notizen (free text, after a call/meeting)
      ├── ki_zusammenfassung (auto-generated AI summary)
      ├── followup_empfehlung (AI follow-up recommendation)
      └── reminders[] → Reminder

Event
  ├── id, application_id, typ (interview | email | phone | note)
  ├── datum, notiz, google_calendar_event_id
  └── next_step (text, due_date)

Reminder
  ├── id, application_id or contact_id, text, due_date
  ├── kanal (email | push | calendar)
  └── erledigt_flag (done flag)
```

---

## 5. Integration Architecture

### LinkedIn
- **Short term:** continuation of the existing browser scraping via Claude in Chrome (no official API access for private users)
- **Medium term:** Playwright-based headless scraper as a Celery task (triggered daily or manually)
- Mapping LinkedIn status → internal status enum

### Gmail
- Google OAuth 2.0 for read access
- Search for application-relevant emails (filters: "rejection", "interview", "appointment", "invitation")
- Automatic linking of email ↔ application via company/role in the subject line
- Attachments (job postings) optionally saved

### Google Calendar
- Read and write access via Google Calendar API
- Automatically create interviews + follow-up dates as events
- Two-way sync: changes in the calendar are reflected in the app

### Company Profiles (Web Research)
- Clearbit Company API (free up to 2,500 requests/month)
- Fallback: own web search (DuckDuckGo API or SerpAPI)
- LinkedIn company scraping for logo + employee count
- Cache in PostgreSQL (no re-fetch within 30 days)

---

## 5b. Contact Management (CRM Module) – Detail

### Data Sources & Enrichment Flow

Every contact entry is automatically assembled from multiple sources:

1. **vCard / CSV import** (phone contact list): name + phone number as the base
2. **Gmail signature parser**: Celery task parses signatures of incoming emails → extracts role, company, email, phone
3. **LinkedIn scraper**: photo, current title, career history
4. **Google Calendar**: appointments with the contact are automatically linked as interactions
5. **Manual**: personal notes, impressions after calls, tags

Dedup logic: merging via `email` (primary), `linkedin_id`, `vcard_uid` — prevents duplicate entries when the same person comes from multiple sources.

### Contact Types & Roles

- **HR / Recruiting** – first contact, coordinates the process
- **Headhunter** – external recruiter (linked to the headhunter firm, not the target company)
- **Fachbereich (FB) / hiring department** – future manager / colleague in the interview
- **C-Level** – decision-maker (CEO, CTO, etc.)
- **Network** – no active application context, but worth keeping relevant

### AI Features per Contact

- **Conversation summary**: Claude summarizes meeting notes in 2–3 sentences
- **Follow-up recommendation**: "Still no reply after 14 days → friendly follow-up email"
- **Detecting shared topics**: interests/focus areas extracted from email history
- **Relationship-strength score**: computed from contact frequency, response time, conversation depth

### Views in the Frontend

- **Contact list**: filterable by type, company, warmth, last contact
- **Contact detail**: timeline of all interactions (emails, calls, meetings), linked applications, AI summary
- **Network map**: visual representation: contact ↔ company ↔ application
- **Follow-up queue**: who needs a response today / this week?

---

## 6. Frontend Modules

```
/dashboard        → Kanban + table view, quick actions
/applications/:id → detail page: timeline, contacts, notes, next steps
/contacts         → CRM contact list, filterable, follow-up queue
/contacts/:id     → contact detail: profile, interaction history, AI insights
/companies/:id    → company profile + all applications + contacts at this company
/analytics        → KPI charts, funnel analysis, AI insights
/calendar         → agenda view, Google Cal sync status
/settings         → OAuth connections, sync intervals, notifications
/import           → Excel upload + vCard import + mapping wizard
```

---

## 7. Deployment

```yaml
# docker-compose.yml (simplified)
services:
  app:       # FastAPI backend (port 8000)
  frontend:  # React build (nginx, port 3000)
  db:        # PostgreSQL
  redis:     # Celery broker
  celery:    # background worker
  nginx:     # reverse proxy (port 443, HTTPS)
```

**Start:** `docker compose up -d`
**Access:** `https://jobs.local` or a custom domain
**Backup:** daily PostgreSQL dump as a cron job, optionally to Google Drive

---

## 8. Development Roadmap

| Phase | Content | Effort |
|---|---|---|
| **Phase 1 – MVP** | Excel import, CRUD for applications, simple dashboard | ~3–4 weeks |
| **Phase 2 – Sync** | LinkedIn scraper, Gmail integration, reminder system | ~2–3 weeks |
| **Phase 3 – Enrichment** | Google Calendar, company profiles, contacts | ~2 weeks |
| **Phase 4 – Analytics** | KPI charts, AI insights (Claude API), funnel analysis | ~2 weeks |
| **Phase 5 – Polish** | Mobile-optimized UI, notifications, backup automation | ~1 week |

**Total effort (side project):** approx. 10–12 weeks at approx. 5–8h/week

---

## 9. Next Steps

1. **Decision:** Raspberry Pi or VPS as the hosting platform?
2. **Create repo:** scaffold a GitHub repository with the project structure
3. **Start Phase 1:** set up FastAPI project + React/Vite skeleton + Docker Compose
4. **Import Excel:** load the existing 133 entries as initial data

---

*This document is the original planning concept from June 10, 2026 and is deliberately no longer updated — it serves as a starting-point reference. The current state is maintained in [ARCHITECTURE.md](ARCHITECTURE.md).*
