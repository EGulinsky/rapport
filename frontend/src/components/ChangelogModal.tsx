import { X } from 'lucide-react'

interface Release {
  version: string
  date: string
  changes: string[]
}

const CHANGELOG: Release[] = [
  {
    version: '2.0.15',
    date: '2026-06-16',
    changes: [
      'Fix: Kalendertermine schlagen keine Statusänderungen mehr in der Prüfung vor — Termine sind Einträge, keine Status-Kommunikation',
    ],
  },
  {
    version: '2.0.14',
    date: '2026-06-16',
    changes: [
      'Feature: Nächster Schritt — intelligentes berechnetes Feld in Tabelle und Kanban (zukünftige Termine, Feedback-Status, Ghosting-Warnung, Stage-basierte Empfehlung)',
    ],
  },
  {
    version: '2.0.13',
    date: '2026-06-16',
    changes: [
      'Fix: Letztes Update ignoriert jetzt zukünftige Termine — zeigt die letzte tatsächliche Aktivität, nicht den nächsten geplanten Termin',
    ],
  },
  {
    version: '2.0.12',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Archived → Abgesagt jetzt für alle Stages (nicht nur Früh-Phase) — unabhängig vom bisherigen Status',
    ],
  },
  {
    version: '2.0.11',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Scraper — neuer JS-basierter Ansatz für LinkedIn-Job-Extraktion (layout-stabil, Cookie-Consent wird automatisch weggedrückt)',
    ],
  },
  {
    version: '2.0.10',
    date: '2026-06-16',
    changes: [
      'Feature: LinkedIn 2FA inline — App-Push-Notification oder Code aus E-Mail/SMS direkt im App eingeben',
    ],
  },
  {
    version: '2.0.9',
    date: '2026-06-16',
    changes: [
      'UX: Einstellungen auf Sidebar-Layout umgestellt — skaliert sauber auf viele Tabs',
      'Feature: LinkedIn-Tab in Einstellungen — Konfiguration und Sync direkt dort',
    ],
  },
  {
    version: '2.0.8',
    date: '2026-06-16',
    changes: [
      'Feature: LinkedIn Sync zeigt nach Abschluss ein detailliertes Aktionslog (Neu / Abgesagt / Aktualisiert)',
      'Fix: LinkedIn-Archiv-Einträge werden jetzt korrekt als Absage markiert (abgesagt=true, Status=rejected) wenn Bewerbung noch in Früh-Phase (beworben/prospecting)',
    ],
  },
  {
    version: '2.0.7',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Login — networkidle durch domcontentloaded ersetzt (LinkedIn erreicht nie networkidle wegen Background-Requests)',
    ],
  },
  {
    version: '2.0.6',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Login — warte auf networkidle statt domcontentloaded, dann explizit auf #username mit 10s Timeout',
    ],
  },
  {
    version: '2.0.5',
    date: '2026-06-16',
    changes: [
      'Perf: Playwright-Chromium in separates Docker-Base-Image ausgelagert — wird nur neu gebaut wenn sich Playwright-Version oder Dockerfile.playwright-base ändert',
      'Perf: Normale Deploys überspringen Chromium-Download komplett (~10 min gespart)',
    ],
  },
  {
    version: '2.0.4',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Login-Timeout — warte explizit auf React-Formular-Hydration bevor Felder befüllt werden',
    ],
  },
  {
    version: '2.0.3',
    date: '2026-06-16',
    changes: [
      'Perf: Sync-Quellen laden bereits indizierte IDs einmalig in ein Set statt pro Element eine DB-Query',
      'Perf: Fortschritts-Updates nur alle 10 Elemente statt jeden Schritt (weniger DB-Writes)',
      'Perf: is_synced-Check in gcal/iCloud-Kalender kommt jetzt vor dem Keyword-Filter',
    ],
  },
  {
    version: '2.0.2',
    date: '2026-06-16',
    changes: [
      'Fix: Lokale Dokumente Toggle-Zustand wird jetzt korrekt gespeichert und geladen',
    ],
  },
  {
    version: '2.0.1',
    date: '2026-06-16',
    changes: [
      'Fix: Tab „Dokumente" in Einstellungen war abgeschnitten — Tab-Leiste ist jetzt horizontal scrollbar',
    ],
  },
  {
    version: '2.0.0',
    date: '2026-06-16',
    changes: [
      'Neues Sync-System: Deterministische Klassifizierung ersetzt KI für ~90% der Fälle (Kalender, lokale Dateien, Einzel-Firmenzuordnung)',
      'Hintergrund-Sync: Automatische Indizierung alle 20 Minuten via asyncio-Loop',
      'Neue Quelle: Lokale Bewerbungsunterlagen (PDF, DOCX, TXT, MD) via files_bridge.py auf Port 9998',
      'Einstellungen → Tab „Dokumente": Ordnerpfad konfigurieren, Bridge-Status, manueller Sync',
      'Sync-Steuerung: Neuer Toggle „Lokale Dokumente" im Sync-Steuerungs-Panel',
      'Leere Firmenzuordnung → sofortige KI-Umgehung statt unnötiger API-Calls',
    ],
  },
  {
    version: '1.0.8',
    date: '2026-06-14',
    changes: [
      'Fix: Kurzformen von Firmennamen mit 4–5 Zeichen (z.B. „Opitz") werden jetzt im Suchindex erfasst',
    ],
  },
  {
    version: '1.0.7',
    date: '2026-06-14',
    changes: [
      'Sync-Steuerung: Google / Apple / LinkedIn gesamt und einzelne Quellen ein-/ausschaltbar',
      'Neuer Tab „Sync-Steuerung" in den Einstellungen mit Master-Toggles und Unterquellen',
      'SyncButton überspringt deaktivierte Quellen beim globalen Sync',
    ],
  },
  {
    version: '1.0.6',
    date: '2026-06-14',
    changes: [
      'Apple Notes Sync: Pre-Filter überspringt Notizen ohne Firmennamen-Treffer (kein KI-Call)',
      'Apple Notes Sync: parallele KI-Calls in Batches à 5 statt sequenziell',
    ],
  },
  {
    version: '1.0.5',
    date: '2026-06-13',
    changes: [
      'Eigener Kontakt wird beim Sync übersprungen (Google-, iCloud- und LinkedIn-Account)',
      'Google-E-Mail wird nach OAuth gespeichert (Userinfo-API) und als Owner-Adresse erkannt',
      'googlemail.com ↔ gmail.com werden als gleiche Adresse behandelt',
    ],
  },
  {
    version: '1.0.4',
    date: '2026-06-13',
    changes: [
      'Kanban: Reihenfolge innerhalb einer Spalte nach letztem Update (neu → alt)',
    ],
  },
  {
    version: '1.0.3',
    date: '2026-06-13',
    changes: [
      'Kalender-Wochenansicht: feste Spaltenhöhe, jede Tagesspalte scrollt unabhängig',
    ],
  },
  {
    version: '1.0.2',
    date: '2026-06-13',
    changes: [
      'Kalender zeigt nur echte Termine (Gespräch, gcal, iCloud Cal) – keine Mails, Notizen oder Statuswechsel',
    ],
  },
  {
    version: '1.0.1',
    date: '2026-06-13',
    changes: [
      'Fix: Sync-Fortschritt zeigte Daten anderer Bewerbungen (z.B. Hahn-Schickard statt Moog)',
    ],
  },
  {
    version: '1.0.0',
    date: '2026-06-13',
    changes: [
      'Kalender-View: Tag / Arbeitswoche / Woche / Monat (Outlook-Stil)',
      'Events farbkodiert nach Bewerbungs-Status',
      'Klick auf Termin öffnet Detail-Modal mit Bewerbungslink',
      'Backend: GET /api/calendar/events mit Datumsfilter',
      'Auto-Deploy via GitHub Actions + self-hosted Runner (SSH-Auth)',
    ],
  },
  {
    version: '0.9.0',
    date: '2026-06-13',
    changes: [
      'GitHub-Repo + CI/CD Pipeline (ruff, tsc, Docker Buildx)',
      'Technische Architekturdokumentation (docs/ARCHITECTURE.md)',
      'Projektstand-Dokument aktualisiert und ins docs/-Verzeichnis verschoben',
      'Alle ruff-Lintfehler behoben (E402, E702, E712, F401, F811, F821)',
    ],
  },
  {
    version: '0.8.0',
    date: '2026-06-13',
    changes: [
      'Versionsnummer + Changelog-Modal im Header',
      'Lifecycle-Bar in Bewerbungsdetail (horizontaler Fortschritt)',
      'Letztes Update dynamisch aus max(Timeline-Event) berechnet',
      'Uhrzeit bei Mail-Events in der Timeline (HH:MM Uhr)',
      'ID als eigene Spalte in Tabelle und Kanban-Karten',
      'Letztes Update im Kanban unten in den Karten',
    ],
  },
  {
    version: '0.7.0',
    date: '2026-06-12',
    changes: [
      'Kontaktübersicht: Firma als eigene Spalte, Sortierung nach Name/Firma/Typ/Letzter Kontakt',
      'Kontakt-Upsert aus Mail-/Kalender-Sync (Name, E-Mail, Telefon, Rolle aus Footer)',
      'Targeted Sync: Pro-Bewerbung alle Quellen parallel synchronisieren',
      'LinkedIn Playwright-Scraper mit gecachten Session-Cookies',
      'Anrufhistorie via calls_bridge.py (macOS CallHistoryDB)',
      'iCloud Notizen via notes_bridge.py (AppleScript/JXA)',
    ],
  },
  {
    version: '0.6.0',
    date: '2026-06-11',
    changes: [
      'Google OAuth 2.0 + Gmail + Google Calendar Sync',
      'iCloud Mail (IMAP), Kalender (CalDAV), Kontakte (CardDAV)',
      'KI-Klassifikation via LiteLLM (Groq, Ollama, OpenAI-kompatibel)',
      'Review-Queue für KI-Vorschläge mit manueller Freigabe',
      'Fernet-Verschlüsselung für alle Credentials und API-Keys',
      'Dedup via synced_items-Tabelle (source + external_id)',
    ],
  },
  {
    version: '0.5.0',
    date: '2026-06-10',
    changes: [
      'Excel-Export im Originalformat (17 Spalten, Sheet "Tracking")',
      'Kontaktverwaltung (CRM): n:m-Verknüpfung mit Bewerbungen',
      'Dubletten-Bereinigung für Bewerbungen, Kontakte und Events',
      'Status-Popover: Statuswechsel direkt in der Tabellenzeile',
      'AI-Settings-Modal: Provider, Modell, API-Key, Verbindungstest',
    ],
  },
  {
    version: '0.4.0',
    date: '2026-06-09',
    changes: [
      'Zweistufiges Statusmodell: main_status + sub_status',
      'Migration alter Flat-Status (hr_scheduled → hr + 1_scheduled)',
      'Sub-Status-Sequenz in HR- und FB-Stages (1_scheduled → 1_done → …)',
      'Automatisches Status-Event bei Statuswechsel',
      'KPI-Kacheln in StatsBar',
    ],
  },
  {
    version: '0.3.0',
    date: '2026-06-08',
    changes: [
      'Kanban-Board nach main_status-Spalten',
      'Detail/Edit-Modal mit Timeline und Gesprächsnotizen',
      'Farbige Status-Badges',
    ],
  },
  {
    version: '0.2.0',
    date: '2026-06-07',
    changes: [
      'Excel-Import (Bewerbungen_Eugen_Gulinsky.xlsx, 133 Einträge)',
      'Sortierbare Tabellenansicht',
      'Suchfilter (Firma, Rolle, Quelle)',
    ],
  },
  {
    version: '0.1.0',
    date: '2026-06-06',
    changes: [
      'FastAPI Backend + SQLite (WAL)',
      'CRUD-Endpunkte für Bewerbungen und Events',
      'React 18 + TypeScript + Tailwind CSS Frontend',
      'Docker Compose + OrbStack-kompatibel',
    ],
  },
]

export const CURRENT_VERSION = CHANGELOG[0].version

interface Props {
  open: boolean
  onClose: () => void
}

export function ChangelogModal({ open, onClose }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <span className="font-semibold text-gray-900">Changelog</span>
            <span className="ml-2 text-xs text-gray-400">JobTracker</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-5">
          {CHANGELOG.map((r, i) => (
            <div key={r.version}>
              <div className="flex items-center gap-3 mb-2">
                <span className={`font-mono font-bold text-sm ${i === 0 ? 'text-indigo-600' : 'text-gray-700'}`}>
                  v{r.version}
                </span>
                {i === 0 && (
                  <span className="text-[10px] font-semibold bg-indigo-100 text-indigo-600 rounded px-1.5 py-0.5">
                    aktuell
                  </span>
                )}
                <span className="text-xs text-gray-400 ml-auto">{r.date}</span>
              </div>
              <ul className="space-y-1">
                {r.changes.map((c, j) => (
                  <li key={j} className="flex gap-2 text-sm text-gray-600">
                    <span className="text-gray-300 mt-0.5 flex-shrink-0">–</span>
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
              {i < CHANGELOG.length - 1 && <div className="mt-4 border-t border-gray-100" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
