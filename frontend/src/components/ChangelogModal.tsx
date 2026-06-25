import { X } from 'lucide-react'
import { BUILD_NUMBER } from '../version'

interface Release {
  version: string
  date: string
  changes: string[]
}

const CHANGELOG: Release[] = [
  {
    version: '2.6.3',
    date: '2026-06-25',
    changes: [
      'PDF-Export: Landscape-Format (A4 quer), breitere Spalten, Überlaufschutz mit Ellipsis',
      'PDF-Export: Terminübersicht der letzten 4 Wochen (Gespräche & Anrufe) nach der Bewerbungsliste',
      'Fix: LI-Sync hat stellenanzeige_url bei bestehenden Bewerbungen nicht nachgetragen — wird jetzt beim nächsten Sync befüllt, falls noch leer.',
      'Fix: LI-Sync Aktionslog zeigte keine Firma/Rolle — werden jetzt korrekt aus der DB-Bewerbung übernommen.',
    ],
  },
  {
    version: '2.6.1',
    date: '2026-06-24',
    changes: [
      'Dokumente als eigener Bereich unterhalb der Timeline — nicht mehr als Timeline-Ereignisse',
      'Klick auf Datei öffnet sie direkt in der zugehörigen Mac-Anwendung (PDF → Vorschau, DOCX → Word, …)',
      'Datei-Zeile zeigt Dateiname, Erweiterung und Löschen-Button (erscheint beim Hover)',
    ],
  },
  {
    version: '2.6.0',
    date: '2026-06-24',
    changes: [
      'Backup: automatische und manuelle DB-Sicherung in einen konfigurierbaren Mac-Ordner',
      'Einstellungen › Backup: Ordner, Frequenz (stündlich bis wöchentlich), Anzahl zu behaltender Backups, "Jetzt sichern"-Button, Liste vorhandener Backups',
      'Scheduler: Backup läuft automatisch im Hintergrund wenn aktiviert und fällig',
    ],
  },
  {
    version: '2.5.8',
    date: '2026-06-24',
    changes: [
      'Fix: last_sync wurde nach jedem Sync-Lauf gesetzt, auch wenn 0 Dateien angelegt wurden — dadurch wurden alle Dateien beim nächsten Sync via since-Filter permanent übersprungen. last_sync wird jetzt nur noch gesetzt wenn mindestens eine Datei neu angelegt wurde.',
    ],
  },
  {
    version: '2.5.7',
    date: '2026-06-24',
    changes: [
      'Fix: DB-Migration setzte main_status bei jedem Container-Neustart auf den alten Wert zurück, wenn die legacy-Spalte "status" noch befüllt war — betroffen war z.B. Rohde & Schwarz #119 (manuell auf "beworben" gesetzt, nach Deploy wieder "abgesagt"). Alte Spalte wird jetzt beim ersten Start gedroppt; Migration überschreibt nur noch Zeilen mit NULL-Status.',
    ],
  },
  {
    version: '2.5.6',
    date: '2026-06-24',
    changes: [
      'Auto-Sync Dokumente: Ordner werden jetzt auch nach Stelle disambiguiert — bei mehreren Bewerbungen für die gleiche Firma wird der Ordnername gegen den Rollentitel geprüft (Bsp: "Siemens Senior Software Engineer"). Rekursiv: alle Dateien in beliebig tiefen Unterordnern werden erfasst.',
    ],
  },
  {
    version: '2.5.5',
    date: '2026-06-24',
    changes: [
      'Auto-Sync Dokumente: Ordner eine Ebene unterhalb des konfigurierten Stammordners werden direkt als Bewerbungsordner behandelt — Ordnername wird gegen Firmennamen gematcht, alle Dateien darin werden als Ereignis (Typ "Datei") angehängt, ohne dateiweise KI/Keyword-Analyse',
    ],
  },
  {
    version: '2.5.4',
    date: '2026-06-24',
    changes: [
      'Dokumentensync manuell: Browser startet im konfigurierten Stammordner, erlaubt aber freie Navigation im gesamten Dateisystem (Pfadleiste mit Klick-Navigation, "nach oben"-Pfeil, "↩ Startordner"-Taste)',
      'Ordner komplett hinzufügen: + Button neben jedem Ordner hängt alle Dateien darin rekursiv an die Bewerbung an',
    ],
  },
  {
    version: '2.5.3',
    date: '2026-06-24',
    changes: [
      'Audit-Log: SQLite-Trigger fängt jede main_status-Änderung auf DB-Ebene ab — auch wenn der Python-Codepfad keinen Eintrag erzeugt (Eintrag erscheint dann mit source="db_trigger")',
      'Modal: Speichern überträgt nur tatsächlich geänderte Felder, verhindert ungewolltes Überschreiben des Status durch veralteten Modal-Zustand',
      'Merge: Statusänderung durch field_overrides wird jetzt explizit als status_change geloggt',
    ],
  },
  {
    version: '2.5.2',
    date: '2026-06-24',
    changes: [
      'Dokumentensync: Auto-Sync gleicht Dateien jetzt anhand des direkten Unterordners im Dokumenten-Stammordner ab (nicht mehr anhand des unmittelbaren Elternordners)',
      'Dokumentensync: Manueller Sync — neuer "Dokument hinzufügen"-Button im Sync-Menü jeder Bewerbung öffnet einen Datei-Browser mit Ordnernavigation unterhalb des konfigurierten Stammordners',
      'Files Bridge: neue Endpoints /browse (Ordner-/Dateiliste ohne Textextraktion) und /file (einzelne Datei mit Textinhalt)',
    ],
  },
  {
    version: '2.5.1',
    date: '2026-06-24',
    changes: [
      'LI-Sync: "No longer accepting applications" und "Stelle nicht mehr verfügbar" werden ignoriert — diese Meldungen betreffen den Status der Stellenanzeige, nicht den eigenen Bewerberstatus im Tracker',
    ],
  },
  {
    version: '2.5.0',
    date: '2026-06-24',
    changes: [
      'Audit-Log: vollständiges Änderungsprotokoll für alle Bewerbungen — wann, durch wen (Quelle) und warum wurde was geändert',
      'Erfasst: Statusänderungen (manuell + via PendingMatch), Anlegen, Löschen, Zusammenführen, Excel-Import, LI-Sync-Neuanlage',
      'Log-Stufe in den Einstellungen wählbar: Aus / Normal (Standardwert) / Ausführlich (+ alle Feldänderungen)',
      'Audit-Log-Button im Header (Klemmbrett-Symbol) öffnet globale Ansicht mit Filtern nach Bewerbung und Pagination',
    ],
  },
  {
    version: '2.4.7',
    date: '2026-06-24',
    changes: [
      'Fix: Normaler Sync erstellte bei jeder neuen Absage-E-Mail einen neuen Review-Vorschlag — fehlender already_reviewed-Check (analog zum LI-Sync-Fix) in _save_deterministic_event, process_item (AI-Pfad) und save_classified_event; Absage-Vorschläge pro App+Zielstatus werden jetzt nach einmaliger Review-Entscheidung nicht mehr neu erstellt',
    ],
  },
  {
    version: '2.4.6',
    date: '2026-06-24',
    changes: [
      'Fix: LI-Sync legte neue Bewerbungen aus der Archiviert-Kategorie direkt als "Abgesagt" an — jetzt werden sie als "Beworben" angelegt und ein Review-Vorschlag erstellt (betrifft auch status_hint="rejected" bei Neu-Anlage)',
    ],
  },
  {
    version: '2.4.5',
    date: '2026-06-24',
    changes: [
      'Syncs ändern Bewerbungsstatus nie mehr automatisch — alle Statusvorschläge (normaler Sync, gezielter Sync, LI-Sync) landen in der manuellen Review-Queue (PendingMatch); gezielter Sync hat diese Logik jetzt ebenfalls (war vorher still ignoriert)',
    ],
  },
  {
    version: '2.4.4',
    date: '2026-06-24',
    changes: [
      'Fix: Gezielter Sync (Sync-Button im Modal) berücksichtigt jetzt Merge-Aliases — E-Mails mit dem alten Firmennamen zusammengeführter Bewerbungen werden korrekt gefunden',
    ],
  },
  {
    version: '2.4.3',
    date: '2026-06-24',
    changes: [
      'Fix: Checkboxen in Tabellenansicht konnten keine Einträge auswählen — TD-onClick und Input-onChange riefen beide onToggleSelect auf, Auswahl wurde sofort wieder aufgehoben',
    ],
  },
  {
    version: '2.4.2',
    date: '2026-06-24',
    changes: [
      'Fix: Bewerbung wurde nach jedem LI-Sync erneut als "Abgesagt" vorgeschlagen, obwohl der Vorschlag bereits abgelehnt/genehmigt war — jetzt werden bereits reviewte Vorschläge (approved/rejected) pro App+Zielstatus nicht mehr neu angelegt (behebt Rohde+Schwarz #119)',
    ],
  },
  {
    version: '2.4.1',
    date: '2026-06-24',
    changes: [
      'Abgesagte Bewerbungen: erscheinen beim Einblenden in der Spalte ihres letzten aktiven Status (kein separates "Abgesagt"-Spalte mehr) — rot markiert (Rahmen, Durchstreichung, Hintergrund) sowohl in Kanban als auch Tabelle',
      'Merge-Funktion: Bewerbungen und Kontakte zusammenführen — 2+ Einträge auswählen (Tabelle: Checkboxen), Merge-Dialog zeigt Felder nebeneinander, pro Feld auswählen welcher Wert übernommen wird; Ereignisse und Kontakte werden automatisch zusammengeführt',
      'Merge-Alias: nach dem Mergen werden die alten Bezeichnungen gespeichert — zukünftige Syncs (LI und normal) erkennen die ursprünglichen Firmen-/Stellennamen und legen keine Duplikate mehr an',
      'LinkedIn-Sync: Fortschrittsanzeige pro Stufe — während Scraping: Seite X — Y gefunden pro Kategorie; nach jeder Kategorie: Treffer-Tabelle mit Zählern; während Verarbeitung: Fortschrittsbalken X/Y',
      'Fix Duplikaterkennung: Firma + Stelle müssen normalisiert gleich sein (nicht Substring) — GmbH/AG/SE etc. werden ignoriert, Gendermarker (m/w/d) aus Stelle entfernt; gilt für LI-Sync und Excel-Import',
      'Ghosting bei Abgesagten: auch abgesagte Bewerbungen mit >= 14 Tagen Lücke zwischen Bewerbung und Absage werden als Ghosting markiert; "Nur Ghosting"-Filter lädt jetzt auch abgesagte',
      'Fix: Ghosting-Filter zeigte keine Einträge — letztes_update wurde in-memory durch Sync-Event (Bewerbung eingereicht, datum=heute) überschrieben bevor Ghosting serialisiert wurde',
      'Stellenanzeige-URL: neues Feld in Bewerbungsmaske — Link zur Ausschreibung, manuell editierbar; LinkedIn-Sync befüllt es automatisch',
      'Ghosting: wird jetzt automatisch berechnet (letztes_update > 14 Tage, kein Terminalstatus) — kein manuelles Setzen mehr nötig; neuer "Nur Ghosting"-Filter statusübergreifend',
      'Abgesagt-Flag: jetzt computed property (main_status == rejected) — keine redundante Checkbox mehr, kein Sync-Aufwand',
      'Sync-Fix: abgesagte Bewerbungen aus Firmenindex ausgeschlossen — verhindert Cross-Match bei mehreren Bewerbungen derselben Firma (z.B. Rohde+Schwarz)',
      'LinkedIn-Sync: Parsing auf Firma·Ort-Anker umgestellt — findet alle Einträge unabhängig davon ob eine Notiz vorhanden ist (behebt fehlende Interview-Einträge)',
    ],
  },
  {
    version: '2.2.0',
    date: '2026-06-23',
    changes: [
      'LinkedIn-Sync: Komplett-Umstellung auf text-basiertes Parsing (inner_text + "Add note"-Trenner) — ersetzt fragiles JS-DOM-Scraping; liest Firma, Stelle, Ort, Beworben-Datum und Statushinweise direkt aus dem Seitentext',
      'LinkedIn-Sync: Dedup-Key jetzt Firma + Stelle (statt LinkedIn-Job-ID) — robuster gegen URL-Änderungen',
      'LinkedIn-Sync: Paginierung vereinfacht — nur noch Next-Button-Klick, kein Scrolling mehr nötig',
    ],
  },
  {
    version: '2.1.0',
    date: '2026-06-17',
    changes: [
      'Issue #1: Unterschriftsfeld aus PDF-Export entfernt',
      'Issue #2: Kalender-Änderungserkennung — verschobene/gelöschte Termine werden beim Sync automatisch im Timeline aktualisiert/entfernt (iCloud Kalender + Google Kalender)',
      'Issue #3: Manuell zuordnen — neuer Button im Sync-Dropdown öffnet Kandidaten-Panel mit Direktzuordnung ohne KI; Konfliktabfrage wenn Eintrag bereits in anderer Bewerbung',
      'Issue #4: Duplikat-Bereinigung erweitert — Kontakte nach Namen, bewerbungsübergreifende Events per external_id; beide gehen in manuelle Nachbearbeitung statt automatischer Löschung',
      'Issue #5: Dateianhänge — Anhänge werden im Container gespeichert, im Timeline angezeigt und können heruntergeladen werden; >100 MB geht in manuelle Nachbearbeitung',
      'Issue #6: Deep Links in Timeline — Gmail, Google Kalender, iCloud Mail/Kalender/Notizen können direkt in der jeweiligen App geöffnet werden (klickbarer Source-Badge)',
      'Issue #7: Bewerbungsdatum readonly — datum_bewerbung nur noch über Timeline-Ereignis "Bewerbung" setzbar; Änderungen synchronisieren automatisch das Datenbankfeld',
      'Intern: external_id-Feld auf Event-Tabelle für Deep Links und cross-App-Duplikaterkennung',
    ],
  },
  {
    version: '2.0.42',
    date: '2026-06-17',
    changes: [
      'Fix: Alle LinkedIn-Kategorien nutzen jetzt jobs-tracker/?stage= (saved/in-progress/applied/interview/archived) — vollständige Pagination für alle Tabs, keine my-items-URL mehr',
    ],
  },
  {
    version: '2.0.41',
    date: '2026-06-17',
    changes: [
      'Fix: Pagination ARCHIVED — Playwright-nativer Click statt JS-evaluate + wait_for_load_state("networkidle") statt Polling; stale_rounds-Schwelle auf 5 erhöht',
      'Debug: Excel-Export enthält jetzt Sheet "Pagination-Log" mit allen Klick- und Stale-Ereignissen pro Kategorie',
    ],
  },
  {
    version: '2.0.40',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Sync legt keine Duplikate mehr an — jede Bewerbung bekommt beim ersten Sync ihre LinkedIn-Job-ID gespeichert; alle folgenden Syncs matchen primär danach (kein Fuzzy-String-Vergleich mehr nötig)',
    ],
  },
  {
    version: '2.0.39',
    date: '2026-06-17',
    changes: [
      'Neu: LinkedIn-Sync wendet Statusänderungen nicht mehr direkt an — sie landen als "Status-Vorschlag" in der manuellen Überprüfung (LinkedIn-Icon, Text "LinkedIn meldet Status-Änderung:")',
    ],
  },
  {
    version: '2.0.38',
    date: '2026-06-17',
    changes: [
      'Fix: Interviews-Tab — Kontext-Extraktion begrenzt auf 500 Zeichen pro Karte, verhindert dass alle Stellen einer Seite als Kontext einer einzelnen Stelle übernommen werden (führte zu falscher Firma und Schein-Duplikaten)',
    ],
  },
  {
    version: '2.0.37',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper wartet nach "Weiter"-Klick aktiv bis neue Jobs im DOM erscheinen (max. 12 s) — verhindert vorzeitigen Abbruch bei langsamen Seitenübergängen (Archived hatte deshalb zu wenige Ergebnisse)',
      'Fix: Duplikate zwischen Kategorien eliminiert — erscheint dieselbe Stelle in mehreren Tabs (z. B. Beworben + Interviews), wird nur die höherpriore Kategorie übernommen',
    ],
  },
  {
    version: '2.0.36',
    date: '2026-06-17',
    changes: [
      'Fix: Interviews-Sync nutzt jetzt die korrekte URL (linkedin.com/jobs-tracker/?stage=interview) statt der ungültigen ?cardType=INTERVIEWS-URL — LinkedIn ignorierte den Parameter und zeigte fälschlicherweise den Saved-Tab',
    ],
  },
  {
    version: '2.0.35',
    date: '2026-06-17',
    changes: [
      'Debug: LinkedIn-Scraper speichert nach Seitenload das rohe HTML jeder Kategorie nach /tmp/linkedin_capture_CATEGORY.html für Offline-Tests',
    ],
  },
  {
    version: '2.0.34',
    date: '2026-06-17',
    changes: [
      'Fix: "database is locked" beim LinkedIn-Sync — busy_timeout auf 60s erhöht; kritische db.commit()-Aufrufe mit Retry-Logik (bis 5 Versuche) abgesichert',
    ],
  },
  {
    version: '2.0.33',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn Pagination Next-Button per JavaScript gesucht (nicht CSS-Selektor) — funktioniert unabhängig von Locale und LinkedIn-Version',
      'Fix: Job-Extraktion erkennt jetzt auch /jobs/collections/, /jobs/detail/ und data-job-id-Attribute — deckt Interview-Tab-Links ab',
    ],
  },
  {
    version: '2.0.32',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper paginiert APPLIED/SAVED/IN_PROGRESS nur Seite 1 (aktuelle Jobs), ARCHIVED und INTERVIEWS alle Seiten — verhindert dass alte archivierte Jobs als "Beworben" erscheinen',
      'Fix: LinkedIn INTERVIEWS — JS-Extraktion erkennt jetzt auch /jobs/collections/ und andere LI-Job-URL-Typen',
    ],
  },
  {
    version: '2.0.31',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn INTERVIEWS — JS-Extraktion erkennt jetzt auch /jobs/collections/ und andere LI-Job-URL-Typen (nicht nur /jobs/view/); Interview-Karten verwenden andere Link-Formate',
    ],
  },
  {
    version: '2.0.30',
    date: '2026-06-17',
    changes: [
      'Fix: SQLite TypeError beim Erstellen neuer LinkedIn-Bewerbungen — datum_bewerbung/letztes_update als date-Objekt statt String übergeben',
    ],
  },
  {
    version: '2.0.29',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper wartet auf ersten Job-Link im DOM (wait_for_selector) bevor JS läuft — LinkedIn rendert Interview-Karten asynchron, daher wurden nur 1 von 6 gefunden',
    ],
  },
  {
    version: '2.0.28',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn ARCHIVED/INTERVIEWS nutzen Seitenpaginierung (1/2/3/Next), kein Infinite Scroll — Scraper klickt jetzt "Next"-Button durch bevor er scrollt',
    ],
  },
  {
    version: '2.0.27',
    date: '2026-06-17',
    changes: [
      'Debug: LinkedIn-Scraper loggt nach Seitenload alle Buttons, scrollbare Container und Seitenhöhe; nach jedem Scroll-Versuch DOM-Höhe und Job-Link-Anzahl — sichtbar im Sync-Log',
    ],
  },
  {
    version: '2.0.26',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper Scroll — echte Mausrad-Events (page.mouse.wheel) nach scrollIntoView statt End-Taste; triggert LinkedIn IntersectionObserver zuverlässig; stale-Toleranz auf 5 Runden erhöht (war 3)',
    ],
  },
  {
    version: '2.0.25',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper — Scroll nutzt jetzt scrollIntoView auf letztem Job-Card + End-Taste; funktioniert auf "My Jobs"-Seite unabhängig vom Container-Layout',
    ],
  },
  {
    version: '2.0.24',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper — Firmenname zeigte ", Verified" wenn Badge-Text nach Normalisierung leer wurde (ln_norm-Filter ergänzt)',
      'Fix: LinkedIn-Scraper — Scroll trifft jetzt die interne List-Div statt window (LinkedIn lazy-lädt über Container-scrollTop)',
      'Fix: Debug-Excel — Raw-Context-Spalte war leer (_raw_context fehlte im raw-Dict)',
    ],
  },
  {
    version: '2.0.23',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper — Set-basiertes Stale-Tracking (all_dom_ids) ersetzt dom_count; funktioniert auch bei Virtual Scrolling',
      'Fix: Datumsextraktion — JS-Extractor ohne \\n-Bedingung, aria-label-Fallback, Raw-Context als letzter Fallback',
      'Debug: Raw-Context-Spalte im Debug-Excel zeigt was der Scraper aus dem DOM liest',
    ],
  },
  {
    version: '2.0.22',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Scraper scrollt jetzt alle Seiten durch — stale-Erkennung basiert auf DOM-Elementanzahl statt eindeutiger neuer Jobs; scrollTo(scrollHeight) statt scrollBy(800px); "Show more results"-Button wird geklickt',
    ],
  },
  {
    version: '2.0.21',
    date: '2026-06-17',
    changes: [
      'Feature: LinkedIn Debug-Excel nach Sync — alle gefundenen Stellen mit LI Job-ID, Firma, Rolle, Datum, Kategorie, Status-Hint und DB-Aktion; Sheet "Kategorien" zeigt Trefferanzahl pro LI-Kategorie',
    ],
  },
  {
    version: '2.0.20',
    date: '2026-06-17',
    changes: [
      'Fix: LinkedIn-Datumserkennung für bare "m" (2m, 3m, 4m, 5m ago) — sowohl Zeilenfilter als auch Parser ergänzt (mo? deckt m und mo ab)',
    ],
  },
  {
    version: '2.0.19',
    date: '2026-06-17',
    changes: [
      'Fix: Bewerbungsdatum in Tabellenansicht — wird jetzt automatisch aus dem frühesten bewerbung-Event abgeleitet wenn DB-Feld leer ist (trifft v.a. LinkedIn-Einträge)',
    ],
  },
  {
    version: '2.0.18',
    date: '2026-06-16',
    changes: [
      'Feature: PDF-Export "Nachweis der Eigenbemühungen" für die Bundesagentur für Arbeit — Bewerbungen ab 01.02.2026 als strukturierte Liste mit Kopfzeile, Fußzeile und Unterschriftsfeld',
    ],
  },
  {
    version: '2.0.17',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Sync — Archived-Einträge wurden durch geteiltes seen_ids-Set mit früheren Kategorien überschrieben; jetzt pro Kategorie isoliert (ARCHIVED schlägt APPLIED korrekt)',
    ],
  },
  {
    version: '2.0.16',
    date: '2026-06-16',
    changes: [
      'Fix: LinkedIn Scraper — Firma/Rolle-Verwechslung durch ", Verified"-Badge behoben; Datum-Parsing für Kurzformat (6d/2w/1mo) ergänzt',
    ],
  },
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
                  <>
                    <span className="text-[10px] font-semibold bg-indigo-100 text-indigo-600 rounded px-1.5 py-0.5">
                      aktuell
                    </span>
                    <span className="text-[10px] text-gray-400 font-mono">
                      Build {BUILD_NUMBER}
                    </span>
                  </>
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
