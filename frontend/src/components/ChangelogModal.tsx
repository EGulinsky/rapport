import { X } from 'lucide-react'
import { BUILD_NUMBER } from '../version'

interface Release {
  version: string
  date: string
  changes: string[]
}

const CHANGELOG: Release[] = [
  {
    version: '3.21.2',
    date: '2026-07-02',
    changes: [
      'Fix: Der Ort war zwar im Übersicht-Tab sichtbar, aber nicht auf der Kanban-Karte — das Response-Schema der Bewerbungsliste (die auch die Kanban-Karten befüllt) deklarierte das Feld "ort" nicht, wodurch es aus der Antwort gefiltert wurde, obwohl es in der Datenbank gesetzt war.',
    ],
  },
  {
    version: '3.21.1',
    date: '2026-07-02',
    changes: [
      'Der Ort einer Bewerbung wird jetzt auch in der Kanban-Karte unten rechts angezeigt — als Link, der die Adresse direkt in Google Maps öffnet.',
    ],
  },
  {
    version: '3.21.0',
    date: '2026-07-02',
    changes: [
      'Neues Feld "Ort" bei Bewerbungen (optional, sichtbar im Übersicht-Tab). Manuelle Eingabe mit Autocomplete über eine kostenlose Karten-API (OpenStreetMap/Nominatim, kein API-Key nötig). Wird beim LinkedIn-Sync automatisch aus dem Stellenangebot übernommen, ohne einen bereits manuell gepflegten Ort zu überschreiben.',
    ],
  },
  {
    version: '3.20.0',
    date: '2026-07-02',
    changes: [
      'Der separate Firmenfilter (Dropdown-Button) in der Bewerbungs- und Kontaktansicht ist entfallen. Stattdessen bieten die normalen Suchfelder jetzt eine Firmen-Autocomplete: beim Tippen erscheinen passende Firmen zur Auswahl, die den Suchtext direkt übernimmt. Der Sprung von einer Firma zu ihren Bewerbungen/Kontakten (Firmenansicht) funktioniert weiterhin, setzt jetzt aber einfach den Suchtext statt eines separaten Filters.',
    ],
  },
  {
    version: '3.19.2',
    date: '2026-07-01',
    changes: [
      'iCloud-Kontakte-Sync (Follow-up zu v3.19.1): Ein Domain-Match der E-Mail-Adresse gegen die Firmen-Website reichte allein aus, um Kontakte zu importieren — auch wenn zu dieser Firma gar keine Bewerbung existiert (live: 32 EDAG-Kontakte importiert, obwohl 0 Bewerbungen zu EDAG bestehen; die CompanyProfile war nur noch eine Datenleiche). Der Domain-Match zählt jetzt nur noch, wenn die Firma auch tatsächlich mit mindestens einer Bewerbung verknüpft ist.',
    ],
  },
  {
    version: '3.19.1',
    date: '2026-07-01',
    changes: [
      'iCloud-Kontakte-Sync importierte teils hunderte irrelevante Kontakte (live 592, davon 272 allein mit Firma "EDAG Group") — ein reiner Textmatch des ORG-Felds einer vCard gegen den Namen einer bekannten Firma reichte aus, um praktisch das komplette Adressbuch eines früheren Arbeitgebers zu importieren, unabhängig von jeder echten Verbindung zu einer Bewerbung. Ein Firmen-Namens-Match allein zählt jetzt nicht mehr — zusätzlich muss entweder die E-Mail-Domain des Kontakts zur Firmen-Website passen, oder der Kontakt ist tatsächlich in einer Bewerbung erwähnt bzw. per Firmentext verknüpft.',
    ],
  },
  {
    version: '3.19.0',
    date: '2026-07-01',
    changes: [
      'Beim manuellen Suchen und Zuordnen von Sync-Treffern zu einer Bewerbung ("Manuell zuordnen") lassen sich jetzt mehrere Einträge per Checkbox markieren und in einem Schritt gemeinsam importieren, statt sie einzeln anklicken zu müssen. Konflikte einzelner Einträge (bereits mit einer anderen Bewerbung verknüpft) werden übersprungen und gemeldet, der Rest wird trotzdem importiert.',
    ],
  },
  {
    version: '3.18.2',
    date: '2026-07-01',
    changes: [
      'Bereinigen bei Firmen erkannte Tochterfirmen fälschlich als Duplikate, wenn sie sich die Website-Domain der Mutter teilen (z.B. "Siemens Digital Industries Software" unter siemens.com) — selbst wenn die Mutter-Tochter-Beziehung bereits gepflegt war. Bereits verknüpfte Paare werden jetzt ignoriert. Für noch unverknüpfte Duplikate gibt es zusätzlich zum Zusammenführen die neue Option "Als Tochterfirma zuordnen".',
    ],
  },
  {
    version: '3.18.1',
    date: '2026-07-01',
    changes: [
      'Firmen-Sync (endgültig): "Sync" fand bei jedem Klick immer wieder dieselbe Handvoll kleiner/obskurer Firmen ohne Web-Auftreten, weil "fehlende Beschreibung" weiterhin unbegrenzt als Retry-Grund galt (derselbe Fehlertyp wie beim Logo-Fix in v3.17.3, nur an anderer Stelle wieder eingebaut). Ein "done"-Profil wird jetzt nie mehr automatisch auf "pending" zurückgesetzt — weder wegen fehlendem Logo noch fehlender Beschreibung. "Sync" verarbeitet nur noch wirklich neue Firmen, "Re-Sync" bleibt der bewusste Weg für einen erneuten Versuch.',
    ],
  },
  {
    version: '3.18.0',
    date: '2026-07-01',
    changes: [
      'Neue Auswertungen: Größter Pipeline-Engpass wird jetzt explizit hervorgehoben (Stufe mit dem größten absoluten Bewerbungsverlust, nicht nur niedrigste Rate — vermeidet Fehlschlüsse aus kleinen Stichproben). Neuer Chart "Konversion je Übergang" zeigt die Rate für jeden einzelnen Pipeline-Schritt.',
      'Erfolg nach Firmentyp (Startup/Konzern/KMU/Beratung/…) und Firmengröße als eigene Auswertung — Gespräch- und Angebotsquote je Gruppe.',
      'Erfolg nach Rollen-Kategorie: grobe Einordnung aus dem Stellentitel per Keyword-Heuristik (Führung/Senior/Sonstige), da es kein strukturiertes Feld für "Art der Stelle" gibt.',
    ],
  },
  {
    version: '3.17.5',
    date: '2026-07-01',
    changes: [
      'Bereinigen in der Kalenderansicht behandelt jetzt nur noch echte Kalendereinträge (gleiche Definition wie die Kalenderansicht selbst: Termine/Interviews oder Google-/iCloud-Kalender-Quelle) statt aller Timeline-Objekte (Mails, Anrufe, Notizen). Live verifiziert: 33 → 15 Duplikate im Kalender-Scope, die restlichen 18 waren Mail-/Anruf-Duplikate und gehören nicht dorthin.',
    ],
  },
  {
    version: '3.17.4',
    date: '2026-07-01',
    changes: [
      'Bereinigen (Kalender/Timeline): fand echte Duplikate nicht, wenn derselbe synchronisierte Termin/Anruf/Mail bei mehreren Sync-Durchläufen mit unterschiedlichem Typ gespeichert wurde (z.B. "status" und "gespräch" für denselben Kalendertermin). 33 solcher Duplikate live gefunden, die vorher komplett übersehen wurden. Aussagekräftiger Typ (gespräch/termin/anruf) wird beim Zusammenführen jetzt bevorzugt behalten.',
    ],
  },
  {
    version: '3.17.3',
    date: '2026-07-01',
    changes: [
      'Firmen-Sync: Firmen ohne Clearbit-Logo (v.a. kleine Personalberatungen — 101 von 158 betroffen) wurden bei jedem Sync-Klick erneut als "unvollständig" erkannt und neu synct, obwohl die Liste sie bereits als "Synced" zeigte. Logo-Lookup ist deterministisch — ein einmal fehlendes Logo bleibt fehlend. Nur eine fehlende Firmenbeschreibung löst jetzt noch einen Retry aus.',
    ],
  },
  {
    version: '3.17.2',
    date: '2026-07-01',
    changes: [
      'CI: Testergebnisse sind jetzt direkt in der GitHub-Actions-Run-Zusammenfassung sichtbar (Pass/Fail-Zahlen + Namen fehlgeschlagener Tests), ohne die Logs aufklappen zu müssen — für Backend (pytest) und Frontend (vitest), beide über JUnit-XML.',
    ],
  },
  {
    version: '3.17.1',
    date: '2026-07-01',
    changes: [
      'Fix: pytest schlug in echter CI fehl ("No module named app") — lokal mit `python -m pytest` getestet, was das Arbeitsverzeichnis automatisch zu sys.path hinzufügt, CI ruft aber bares `pytest` auf. `pythonpath = .` in pytest.ini ergänzt, gegen exakten CI-Aufruf im Container verifiziert.',
    ],
  },
  {
    version: '3.17.0',
    date: '2026-07-01',
    changes: [
      'Testkonzept Phase 1 umgesetzt: pytest-Grundgerüst mit Test-DB-Isolation, Factories (Bewerbung/Kontakt/Firma/Event), 37 Backend-Tests (Unit/Component/API) und Vitest-Setup mit ersten Frontend-Komponententests. PR-Gate in CI erweitert — läuft in unter 6 Sekunden.',
    ],
  },
  {
    version: '3.16.2',
    date: '2026-07-01',
    changes: [
      'CI: Deploy-Benachrichtigung auf dem Mac zeigt jetzt die volle App-Version (z.B. "v3.16.2") statt nur der Build-Nummer — wie oben links in der App angezeigt.',
    ],
  },
  {
    version: '3.16.1',
    date: '2026-07-01',
    changes: [
      'Gmail-/iCloud-Sync einer Bewerbung fand keine Mails, wenn die automatisch angereicherte Firmen-Website die falsche Domain hatte (z.B. hahn-schickard.com statt .de) — die Suche filterte ausschließlich nach dieser einen Domain. Bestätigte Kontakt-E-Mail-Adressen der Bewerbung fließen jetzt zusätzlich in die Domain-Suche ein, unabhängig von der (ggf. fehlerhaften) Firmenanreicherung.',
    ],
  },
  {
    version: '3.16.0',
    date: '2026-07-01',
    changes: [
      'Firmen-Sync: Fix für v3.15.8 — der Auto-Continue-Poller nach einem Sync-Batch ignorierte die Markierung und synchronisierte trotzdem alle ausstehenden Firmen weiter. Scoped Runs stoppen jetzt nach ihrem eigenen Batch.',
      'LinkedIn-Einrichtung war doppelt (Sync-Dropdown und Options-Menü) — aus dem Sync-Dropdown entfernt, nur noch in den Einstellungen unter "LinkedIn".',
      'Bereinigen-Funktion ist jetzt kontextsensitiv: der Button zeigt und bereinigt nur die Kategorie der aktuellen Ansicht (Bewerbungen/Kontakte/Firmen/Kalender) statt immer alles. Neu: Firmen-Duplikate werden per Website-Domain erkannt (Namensfeld ist bereits eindeutig in der DB) und über die bestehende Merge-Logik zusammengeführt. Bewerbungs-Matching nutzt jetzt dieselbe normalisierte Firmen-/Rollen-Erkennung wie der Rest der App, Kontakt-Matching berücksichtigt zusätzlich die Firma um Namensgleichheit bei unterschiedlichen Personen nicht mehr fälschlich zusammenzuführen.',
    ],
  },
  {
    version: '3.15.8',
    date: '2026-07-01',
    changes: [
      'Firmen: Sync, Re-Sync und "Kontakte verknüpfen" berücksichtigen jetzt die Markierung — bei ausgewählten Firmen laufen alle drei Aktionen nur für die Auswahl statt für die komplette Liste. Ohne Auswahl unverändertes Verhalten (alle Firmen).',
    ],
  },
  {
    version: '3.15.7',
    date: '2026-06-30',
    changes: [
      'Firmenmodal: Änderungen (Bearbeiten, Logo, Kontakte zuordnen) fehlte ein onSaved-Callback — Firmenliste und Bewerbungsansichten zeigten Änderungen erst nach manuellem Reload. Behoben.',
    ],
  },
  {
    version: '3.15.6',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Import: Root-Cause gefunden und gefixt — LinkedIn hasht mittlerweile alle CSS-Klassennamen, dadurch griffen sämtliche bisherigen Firmenname-Selektoren ins Leere. Firmenname wird jetzt über stabile strukturelle Signale gelesen (Link zur Firmen-Seite im Anzeigenkopf, Seitentitel-Pattern) statt über Klassennamen — live an einer echten Headhunter-Anzeige verifiziert (BLACKBULL INTERNATIONAL GmbH korrekt erkannt).',
    ],
  },
  {
    version: '3.15.5',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Import: Fallback für anonymisierte/"confidential" Stellenanzeigen — wenn die Firma im Seitenkopf nicht sichtbar ist, wird zusätzlich der "Hiring Team"/Recruiter-Bereich nach dem zugehörigen Firmennamen durchsucht (Headhunter-Name), bevor das Feld leer bleibt.',
    ],
  },
  {
    version: '3.15.4',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Import: KI-Prompt erkennt Headhunter-Anzeigen jetzt anhand klarer Signale (z.B. "im Auftrag von", "Executive Search" im Firmennamen, anonymisierte Auftraggeber-Beschreibung) und füllt "Zielfirma" mit der verfügbaren Beschreibung statt sie leer zu lassen oder im Kommentar zu verstecken.',
    ],
  },
  {
    version: '3.15.3',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Import: Firmenname wird jetzt strukturell aus dem Seitenkopf der Stellenanzeige gelesen statt von der KI aus dem Beschreibungstext geraten — behebt fehlende Firma bei Headhunter-Postings, die den Auftraggeber im Text anonymisieren ("Ein börsennotierter Technologiekonzern…").',
    ],
  },
  {
    version: '3.15.2',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Import: Firma wird jetzt automatisch mit bestehenden Firmenprofilen abgeglichen oder sauber neu angelegt — bei Neuanlage läuft im Hintergrund einmalig der Firmendaten-Fetch (Beschreibung, Logo, Branche, Standort) an, wie beim regulären Firmen-Sync.',
    ],
  },
  {
    version: '3.15.1',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Import korrigiert: statt Text manuell einzufügen, einfach den Link zur Stellenanzeige eingeben — die Seite wird automatisch über die bestehende LinkedIn-Anmeldung geladen, die KI extrahiert daraus alle Felder.',
    ],
  },
  {
    version: '3.15.0',
    date: '2026-06-30',
    changes: [
      'Jobsuche-Funktion komplett entfernt (Tab, Jobportale-Einstellungen, Backend-Router, Datenmodell). War kein aktiv genutztes Feature mehr.',
      'Neue Bewerbung: "Neu"-Button ist jetzt ein Dropdown mit "Manuell anlegen" und "Aus LinkedIn importieren" — beim LinkedIn-Import wird der kopierte Stellenanzeigen-Text per KI analysiert und Firma, Rolle, Quelle, Headhunter-Flag und Kommentar automatisch vorausgefüllt.',
    ],
  },
  {
    version: '3.14.52',
    date: '2026-06-30',
    changes: [
      'KI-Batchlauf ("KI bewerten"): zeigt jetzt Live-Fortschritt im Button ("KI: 3/27") statt nur einem statischen "KI läuft…" — Backend streamt Fortschritt per SSE, Kanban aktualisiert sich nach jeder Bewertung.',
    ],
  },
  {
    version: '3.14.51',
    date: '2026-06-30',
    changes: [
      'KI-Einstellungen: Modellauswahl-Chips für Groq, Gemini, Anthropic, OpenAI waren bisher nur in der ungenutzten AiSettingsModal-Komponente implementiert — App.tsx rendert tatsächlich SettingsModal. Chip-Auswahl jetzt dort eingebaut, totes AiSettingsModal.tsx entfernt.',
      'KI-Bewertung im Bewerbungsmodal: Kanban-Ansicht und Bewerbungsliste aktualisieren sich jetzt sofort nach "Neu bewerten" (onSaved() wurde nicht aufgerufen).',
    ],
  },
  {
    version: '3.14.50',
    date: '2026-06-30',
    changes: [
      'KI-Einstellungen: Modellauswahl-Chips für Groq, Gemini, Anthropic, OpenAI — Modelle jetzt direkt im Provider-Array statt in separatem Dictionary (robusterer Lookup).',
    ],
  },
  {
    version: '3.14.49',
    date: '2026-06-30',
    changes: [
      'KI: Modelle die kein JSON-Modus unterstützen oder nicht existieren geben jetzt eine klare Fehlermeldung (400) statt einen rohen 502-Stacktrace.',
    ],
  },
  {
    version: '3.14.48',
    date: '2026-06-30',
    changes: [
      'KI-Bewertung: UI-Refresh nach "Neu bewerten" funktioniert jetzt — Felder werden direkt aus der API-Antwort in den lokalen State geschrieben, kein zweiter GET-Request mehr.',
    ],
  },
  {
    version: '3.14.47',
    date: '2026-06-30',
    changes: [
      'KI-Einstellungen: Modellauswahl-Fix — IIFE-Pattern durch saubere Variablen ersetzt (providerModels/isKnownModel).',
    ],
  },
  {
    version: '3.14.46',
    date: '2026-06-30',
    changes: [
      'KI-Optionen: Rate-Limit und Auth-Fehler werden verständlich angezeigt (nicht mehr als roher JSON-Blob).',
    ],
  },
  {
    version: '3.14.45',
    date: '2026-06-30',
    changes: [
      'KI-Batch: 5 Sekunden Pause zwischen Anfragen bei Gemini/Groq — verhindert Rate-Limit-Fehler. Jede Bewerbung wird direkt nach Bewertung gespeichert.',
      'Rate-Limit-Fehler (429) werden im Modal verständlich angezeigt statt als 502.',
    ],
  },
  {
    version: '3.14.44',
    date: '2026-06-30',
    changes: [
      'KI-Einstellungen: Modellauswahl per Chip für Groq (5 Modelle), Gemini (5 Modelle), Anthropic und OpenAI — analog Ollama. Ausgewähltes Modell wird unterhalb als ID angezeigt.',
    ],
  },
  {
    version: '3.14.43',
    date: '2026-06-30',
    changes: [
      'KI-Einschätzung: neues Feld "Begründung" erklärt warum die Erfolgschance so bewertet wurde (konkrete Fakten aus der Timeline).',
      'KI-Absageanalyse: Bei abgesagten Bewerbungen explizit aufgerufen → analysiert Absagegründe + Optimierungsvorschläge für zukünftige Bewerbungen.',
      'Batch-Bewertung überspringt abgesagte Bewerbungen (main_status=rejected).',
    ],
  },
  {
    version: '3.14.42',
    date: '2026-06-30',
    changes: [
      'KI-Prompt: Heutiges Datum explizit übergeben. Erfundene Daten/Wochentage verboten. next_step verlangt jetzt 2–4 Sätze mit Situationszusammenfassung + Handlungsempfehlung.',
    ],
  },
  {
    version: '3.14.41',
    date: '2026-06-30',
    changes: [
      'KI-Einschätzung: Timeline-Events werden jetzt vollständig (ungekürzt) an die KI übergeben — E-Mail-Inhalt, Kalendernotizen etc.',
      'KI-Einschätzung: Erfolgschance wird jetzt explizit als Text angezeigt ("Hoch / Mittel / Niedrig") in Tabelle, Kanban und Modal.',
    ],
  },
  {
    version: '3.14.40',
    date: '2026-06-30',
    changes: [
      'KI-Einschätzung: Prompt schreibt next_step jetzt als Handlungsanweisung (Imperativ) mit echten Zahlen. Verboten: Status-Labels kopieren, E-Mail-Betreff wiederholen, vage Phrasen.',
      'AI-Logging: Jeder KI-Request und jede Antwort wird mit Kategorie "ai" geloggt (docker logs + Seq).',
    ],
  },
  {
    version: '3.14.39',
    date: '2026-06-30',
    changes: [
      'KI-Einschätzung: bewertet jetzt alle Timeline-Events vollständig (chronologisch, inkl. Betreff und Inhalt). Gesprächsnotizen und Kommentar fließen ebenfalls ein.',
    ],
  },
  {
    version: '3.14.38',
    date: '2026-06-30',
    changes: [
      'KI-Einschätzung: Prompt überarbeitet — berechnet echte Tage, wertet Prozesstiefe (Anzahl Gespräche) und konkrete Timeline aus. Platzierung: im Modal in der Übersicht unten (mit Datum und "Neu bewerten"), in Tabelle/Kanban als Farbpunkt + Text.',
    ],
  },
  {
    version: '3.14.37',
    date: '2026-06-30',
    changes: [
      'KI-Einschätzung: Farbe (grün/gelb/rot) und nächster Schritt pro Bewerbung basierend auf Status und Timeline. Wird nach gezieltem Sync automatisch aktualisiert. "KI bewerten"-Button für alle aktiven Bewerbungen im Header; "KI"-Button pro Bewerbung im Modal.',
    ],
  },
  {
    version: '3.14.36',
    date: '2026-06-30',
    changes: [
      'Firmenname auf Bewerbungen kommt jetzt aus dem Firmenstammdatensatz (name_display) wenn verknüpft — in Tabelle, Kanban, Bewerbungsmodal, Review und Kontaktansichten.',
    ],
  },
  {
    version: '3.14.35',
    date: '2026-06-30',
    changes: [
      'iCloud-Kontaktsync: importiert nur noch relevante Kontakte — Name/E-Mail muss in Bewerbungsereignissen oder -feldern vorkommen, oder Firma muss zu einer Bewerbung oder einem Firmenprofil passen. Adressbuch-Kontakte ohne Jobbezug werden übersprungen.',
    ],
  },
  {
    version: '3.14.34',
    date: '2026-06-30',
    changes: [
      'Firmen: Checkbox "Alle markieren" (filterbewusst), "X löschen"-Button, Anzahl/Auswahl im Footer — analog Kontakte. Kontakte: "Alle markieren" berücksichtigt jetzt aktive Filter.',
    ],
  },
  {
    version: '3.14.33',
    date: '2026-06-30',
    changes: [
      'Kontakte: Filter "Bewerbungen vorhanden" (Alle / Ja / Nein). Firmen: Filter "Bewerbungen vorhanden" und "Kontakte vorhanden" — client-seitig, ohne Backend-Anfrage.',
    ],
  },
  {
    version: '3.14.32',
    date: '2026-06-30',
    changes: [
      'Firma-Picker beim manuellen Anlegen von Bewerbungen und Kontakten: Firmen-Dropdown mit Suche und "Neu anlegen"-Option — analog zum Bearbeitungsmodus. Kontakte-Tab in Firmenprofil hat jetzt Modus-Umschalter "Neu erstellen" / "Vorhandenen zuordnen".',
    ],
  },
  {
    version: '3.14.31',
    date: '2026-06-30',
    changes: [
      'Firmensync: Wikipedia REST API als Fallback wenn DDG nichts liefert. Logo-Fallback via Clearbit (domain-basiert). sync_source zeigt an welche Quelle genutzt wurde.',
    ],
  },
  {
    version: '3.14.30',
    date: '2026-06-30',
    changes: [
      'Cancel-Button für Firmensync und Kontaktverknüpfung — bricht nach dem aktuellen Eintrag graceful ab. Kontaktverknüpfung zeigt jetzt Fortschrittszähler (x/Gesamt).',
    ],
  },
  {
    version: '3.14.29',
    date: '2026-06-30',
    changes: [
      'Firmensync: Wikidata ersetzt durch DuckDuckGo Instant Answer API — kein Rate-Limit, kein API-Key, kein Warten. Liefert Beschreibung, Logo, HQ, Gründungsjahr, Mitarbeiterzahl und Branche aus Wikipedia-Infoboxen.',
    ],
  },
  {
    version: '3.14.28',
    date: '2026-06-30',
    changes: [
      'Firmensync: Retry mit Exponential Backoff bei Wikidata 429/503 (bis 4 Versuche, respektiert Retry-After). Search-API-Abstand auf 1s erhöht, SPARQL-Batch-Pause auf 5s.',
    ],
  },
  {
    version: '3.14.27',
    date: '2026-06-30',
    changes: [
      'Firmensync: Batch-SPARQL — alle Q-IDs werden erst per Search-API gesammelt (0,3s Abstand), dann in einem einzigen SPARQL-Request abgefragt (bis zu 40 Firmen pro Query). Logo-Downloads parallel (max 3 gleichzeitig). Behebt "Too Many Requests" bei größeren Batches.',
    ],
  },
  {
    version: '3.14.26',
    date: '2026-06-30',
    changes: [
      'Firmensync: Logo wird direkt aus Wikidata (P154) geladen und als base64 gespeichert — kein manueller Upload mehr nötig für bekannte Firmen.',
    ],
  },
  {
    version: '3.14.25',
    date: '2026-06-30',
    changes: [
      'Firmensync: KI entfernt — Daten kommen jetzt aus Wikidata (Search-API + SPARQL). Felder: HQ-Stadt/-Land, Gründungsjahr, Mitarbeiterzahl, Website, LinkedIn-URL, Branche, Beschreibung.',
    ],
  },
  {
    version: '3.14.24',
    date: '2026-06-30',
    changes: [
      'Seq-Log: source-Feld pro Sync-Quelle — in Seq nach source = linkedin bzw. source = targeted filtern.',
    ],
  },
  {
    version: '3.14.23',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Sync: Bewerbungsdatum wird für bestehende Apps nachgefüllt, falls noch nicht gesetzt.',
    ],
  },
  {
    version: '3.14.22',
    date: '2026-06-30',
    changes: [
      'Fix: LI-Sync extrahiert Job-ID aus der gescrapten Stellenanzeige-URL (job["stellenanzeige_url"]) — bisher war job["id"] immer leer, URL-basierter Match schlug deshalb nie an.',
    ],
  },
  {
    version: '3.14.21',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Sync individuell: scrapt Kategorie für Kategorie und matcht sofort per LI-Job-ID (aus linkedin_job_id oder stellenanzeige_url) bzw. Firma+Rolle — stoppt nach erstem Match, ohne alle anderen Jobs zu verarbeiten.',
    ],
  },
  {
    version: '3.14.20',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Sync: Bewerbungs-URL (stellenanzeige_url) wird als LI-Job-ID-Quelle genutzt — Match auch wenn linkedin_job_id noch nicht gesetzt.',
      'LinkedIn-Sync pro Bewerbung: stoppt sobald die Ziel-Bewerbung gefunden wurde, überspringt alle anderen Jobs.',
    ],
  },
  {
    version: '3.14.19',
    date: '2026-06-30',
    changes: [
      'Sync pro Bewerbung schließt jetzt auch LinkedIn ein — LI läuft parallel, Fortschrittsbalken und Vorschlag-Zähler erscheinen im Modal.',
    ],
  },
  {
    version: '3.14.18',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Sync: Debug-Excel entfernt — alle Sync-Details (Match-Grund, Kategorie-Zählungen, Paginierung, Fehler) fließen ins strukturierte Log (Seq, Category: sync).',
    ],
  },
  {
    version: '3.14.17',
    date: '2026-06-30',
    changes: [
      'LinkedIn-Sync: Match-Grund (job_id / firma+rolle / alias / neu) pro Eintrag im Log sichtbar.',
      'Wenn ein Status-Vorschlag übersprungen wird (bereits ausstehend / bereits überprüft), steht das jetzt im Log.',
    ],
  },
  {
    version: '3.14.16',
    date: '2026-06-30',
    changes: [
      'Bewerbung: Firmenname ist kein Freitextfeld mehr — nur Zuordnung aus vorhandenen Firmenprofilen oder Neuanlage (analog Kontakte).',
    ],
  },
  {
    version: '3.14.15',
    date: '2026-06-29',
    changes: [
      'Fix: Firma-Merge aktualisiert jetzt app.firma, zielfirma_bei_hh und contact.firma auf den Gewinner-Namen.',
    ],
  },
  {
    version: '3.14.14',
    date: '2026-06-29',
    changes: [
      'Kontakte: Separate Vorname/Nachname-Felder — Sync erkennt "Mehra, Malvika" und "Malvika Mehra" als dieselbe Person.',
      'Kontakte: Bearbeitungsmodal (klick auf Zeile) — alle Felder editierbar analog Firmenprofile.',
      'Kontakte: Bewerbungsformular zeigt Vorname/Nachname als separate Felder.',
    ],
  },
  {
    version: '3.14.13',
    date: '2026-06-29',
    changes: [
      'Sync: Domain-basiertes Matching (Mail/Kalender) statt Kontakt-Index — Datum >= Bewerbungsdatum.',
      'Sync: Kontakte-Sync läuft nach Mail/Cal, sodass Kontakte in neuen Events gefunden werden.',
      'Sync: iCloud Notes — kein "recent 30"-Fallback mehr, nur noch text-matching.',
      'Kontakte: E-Mail ist jetzt Pflichtfeld beim Erstellen und Bearbeiten.',
    ],
  },
  {
    version: '3.14.12',
    date: '2026-06-29',
    changes: [
      'Bewerbungsmodal: Kontakte können jetzt entweder neu erstellt oder aus bestehenden Kontakten zugeordnet werden.',
      'Live-Suche im "Vorhandenen zuordnen"-Modus filtert sofort nach Name, E-Mail oder Firma.',
    ],
  },
  {
    version: '3.14.11',
    date: '2026-06-29',
    changes: [
      'Structured Logging: Loguru ersetzt stdlib logging — JSON auf stdout, alle Logs an Seq weitergeleitet.',
      'Kategorien: sync, ai, backup, app — in Seq nach Kategorie, Level und Zeitraum filterbar.',
      'Seq Log-Viewer läuft auf http://localhost:8088',
    ],
  },
  {
    version: '3.14.10',
    date: '2026-06-29',
    changes: [
      'Detailliertes Sync-Logging: Alle Sync-Quellen (Gmail, GCal, iCloud Mail, iCloud Cal, Notes, Reminders) loggen jetzt per-Item-Entscheidungen im Docker-Log (DEBUG-Level).',
      'Format: [SYNC #<id> <quelle>] <item-id> → SKIP/CREATED/pending mit Betreff, Absender und Grund.',
    ],
  },
  {
    version: '3.14.9',
    date: '2026-06-29',
    changes: [
      'Startup-Check: Beim Laden der App werden alle lokalen Bridges (Files, Notes, Calls) und Verbindungen (Google, iCloud, AI, Lokale Dateien) geprüft.',
      'Fehlende/nicht erreichbare Dienste erscheinen als gelbes Banner mit Details — per Klick aufklappbar, wiederholbar und schließbar.',
    ],
  },
  {
    version: '3.14.8',
    date: '2026-06-29',
    changes: [
      'Sync-Menü: Neuer Eintrag „Sync-Events löschen" — entfernt alle automatisch erzeugten Timeline-Einträge einer Bewerbung, ohne einen neuen Sync zu starten.',
    ],
  },
  {
    version: '3.14.7',
    date: '2026-06-29',
    changes: [
      'Targeted Sync (Gmail, iCloud Mail, iCloud Cal) fällt nicht mehr auf Firmennamen zurück, wenn keine Kontakte verknüpft sind — dadurch keine Fremd-Mails/-Termine mehr durch mehrdeutige Namen (z.B. „HERE" matcht „there").',
      'iCloud Mail: Suche jetzt adressbasiert (Kontakt-Domains/-E-Mails statt Firmenname).',
      'iCloud Cal: Matching jetzt per Organizer/Attendee-E-Mail statt Textsuche im Titel.',
    ],
  },
  {
    version: '3.14.6',
    date: '2026-06-29',
    changes: [
      'AI komplett aus dem Sync entfernt: Mails, Kalendereinträge, iCloud-Notizen und Erinnerungen werden jetzt rein deterministisch klassifiziert (Regex-Muster für Typ, Betreffzeile als Titel).',
      'Kein AI-Fallback mehr bei mehreren gematchten Bewerbungen — der erste Treffer wird verwendet.',
    ],
  },
  {
    version: '3.14.5',
    date: '2026-06-29',
    changes: [
      'Gmail/Kalender-Matching radikal vereinfacht: Mails und Termine werden nur noch anhand von E-Mail-Adressen der verknüpften Kontakte gematcht (exakte Adresse oder Firmendomain) — kein Firmenname-Substring-Matching mehr, das False Positives wie „there" → HERE verursacht hat.',
      'Globaler Gmail-Sync nutzt jetzt einen domainbasierten Suchfilter statt Firmennamen.',
      'Neuer Kontakt wird automatisch angelegt, wenn eine neue Adresse aus einer bekannten Firmendomain erkannt wird.',
    ],
  },
  {
    version: '3.14.4',
    date: '2026-06-29',
    changes: [
      'Gmail: Abgelaufene/widerrufene OAuth-Token werden jetzt erkannt (invalid_grant). Tokens werden automatisch gelöscht und eine klare Meldung mit Hinweis zum Neu-Verbinden erscheint.',
    ],
  },
  {
    version: '3.14.3',
    date: '2026-06-29',
    changes: [
      'Sync-Änderungsanzeige: Nach einem Sync werden nicht nur geänderte Bewerbungen markiert, sondern auch die konkreten Felder hervorgehoben (Amber-Hintergrund + Punkt bei Status, Kommentar, Quelle, Gesprächsnotizen, Stellenanzeige, etc.).',
      'Die Feld-Markierungen verschwinden, sobald die Bewerbung geöffnet wird.',
    ],
  },
  {
    version: '3.14.2',
    date: '2026-06-29',
    changes: [
      'Kanban-Layout: Spalten verteilen sich jetzt automatisch über die gesamte Breite — wenige Spalten füllen den Bildschirm gleichmäßig, viele Spalten scrollen horizontal.',
    ],
  },
  {
    version: '3.14.1',
    date: '2026-06-26',
    changes: [
      'LinkedIn-Nachrichten-Matching korrigiert: Kontaktnamen (aus der Datenbank) werden jetzt als primäres Matching-Signal verwendet — LinkedIn zeigt Personennamen, keine Firmennamen in der Sidebar.',
      'Fallback: Firmenname im Nachrichtenvorschau-Text (≥ 5 Zeichen) für noch unbekannte Recruiter.',
      'Threads werden nur bei tatsächlichem Match geöffnet, kein blindes Öffnen aller Konversationen.',
    ],
  },
  {
    version: '3.14.0',
    date: '2026-06-26',
    changes: [
      'LinkedIn-Sync in den normalen Sync-Button integriert — läuft jetzt automatisch mit allen anderen Quellen.',
      'Neue Datenquelle "linkedin_msg": LinkedIn-Nachrichten werden gescraped und als Timeline-Events (Typ: Mail) verknüpft.',
      '2FA-Eingabe direkt im Sync-Progress-Overlay ohne separaten Dialog.',
      '"LinkedIn einrichten" im Sync-Dropdown öffnet die Konfiguration (Zugangsdaten, Session-Reset).',
    ],
  },
  {
    version: '3.13.1',
    date: '2026-06-26',
    changes: [
      'PDF-Export: Kalendereinträge (Google/iCloud) jetzt vollständig in der Terminübersicht — auch wenn sie vom globalen Sync nicht als "Gespräch" klassifiziert wurden.',
    ],
  },
  {
    version: '3.13.0',
    date: '2026-06-26',
    changes: [
      'Sync-Indikator: Neue oder geänderte Bewerbungen werden nach jedem Sync mit einem pulsierenden Punkt markiert.',
      'Automatisches Öffnen des Prüf-Dialogs wenn nach einem Sync manuelle Aufgaben anfallen.',
      'Review-Zähler: Wird jetzt nach allen Sync-Arten aktualisiert (Einzel-Sync, Firmen-Sync) + 30s-Polling.',
    ],
  },
  {
    version: '3.12.0',
    date: '2026-06-26',
    changes: [
      'Bewerbungsmodal: Tabs Übersicht / Verlauf / Anhänge / Kontakte (analog Firmenmodal).',
      'Verlauf-Tab: Filter nach Zeitraum (1M/3M/6M/1J) und Ereignistyp (Mail, Kalender, Gespräch …).',
      'Anhänge und Kontakte in eigenen Tabs ausgelagert.',
      'Breites Modal (max-w-3xl) für mehr Platz.',
    ],
  },
  {
    version: '3.11.0',
    date: '2026-06-26',
    changes: [
      'Kontakt-Sync: Alle Firmenkontakte vom Rechner werden importiert und im Kontakttab der Firma angezeigt.',
      'Bewerbungs-Verknüpfung nur noch wenn Kontakt explizit in Mails, Kalender oder Bewerbungsnotizen erwähnt wird.',
    ],
  },
  {
    version: '3.10.0',
    date: '2026-06-26',
    changes: [
      'Firmensync: Sync-Aktionen in einem Dropdown zusammengefasst.',
      'Sync: aktualisiert nur ausstehende Firmen und solche mit leeren Feldern.',
      'Re-Sync: setzt alle Firmen zurück und holt alle Daten neu.',
      '"Fehlgeschlagen zurücksetzen" ist jetzt Teil des Sync-Dropdowns.',
    ],
  },
  {
    version: '3.9.0',
    date: '2026-06-26',
    changes: [
      'Firmenfilter in Bewerbungen/Kontakten schließt jetzt auch Tochterunternehmen ein.',
    ],
  },
  {
    version: '3.8.0',
    date: '2026-06-26',
    changes: [
      'Neu: Bulk-Zuweisung von Muttergesellschaft in der Firmenliste — mehrere Firmen auswählen, Muttergesellschaft suchen und zuordnen.',
    ],
  },
  {
    version: '3.7.0',
    date: '2026-06-26',
    changes: [
      'Neu: Hierarchische Firmenstruktur — Muttergesellschaft und Tochterunternehmen verknüpfen.',
      'Firmenprofil: Muttergesellschaft im Bearbeitungsmodus per Suche zuordnen (Zyklenerkennung).',
      'Firmenprofil: Anzeige von Muttergesellschaft und Tochterunternehmen als klickbare Links.',
      'Firmenliste: Kleiner "↑ Konzernname"-Hinweis bei Tochterunternehmen.',
    ],
  },
  {
    version: '3.6.0',
    date: '2026-06-26',
    changes: [
      'Neu: Firmenfilter mit Autocomplete in Bewerbungs- und Kontaktansicht.',
      'Neu: Firmenliste → Bewerbungen/Kontakte öffnet direkt den Firmenfilter in der Zielansicht.',
      'Neu: Kontakte manuell einer Firma zuordnen — aus Kontaktliste und aus Firmenmodal.',
      'Fix: Fehlende Links zur Firma in der Kontaktliste.',
      'Fix: Kontakte werden beim Backend-Start automatisch mit Firmenprofilen verknüpft.',
    ],
  },
  {
    version: '3.5.0',
    date: '2026-06-26',
    changes: [
      'Neu: Firmenmodal mit Tabs (Profil / Bewerbungen / Kontakte) — Kontakte aus verknüpften Bewerbungen.',
      'Neu: Firmen bearbeiten (Anzeigename, Branche, Typ, Mitarbeiter, Standort, Website, Beschreibung).',
      'Neu: Firmen zusammenführen — analog Bewerbungen/Kontakte, Feld-für-Feld-Auswahl.',
      'Neu: Kontaktanzahl in der Firmenliste, Multiselect für Merge.',
    ],
  },
  {
    version: '3.4.1',
    date: '2026-06-26',
    changes: [
      'Neu: Logo.dev als primäre Logo-Quelle (Einstellungen → Logos). Liefert echte Logos inkl. Headhunter-Agenturen; Google Favicons bleibt als Fallback.',
      'Neu: Firmenlogos in der Bewerbungstabelle und im Kanban-Board.',
      'Fix: Firmenlogos in der Firmenliste — Clearbit (abgeschaltet) ersetzt durch Google Favicons.',
    ],
  },
  {
    version: '3.3.8',
    date: '2026-06-25',
    changes: [
      'Neu: Backup-Ordner per Ordner-Picker (nativer macOS-Dialog) auswählen.',
      'Neu: Restore-Button pro Backup — stellt die gesamte Datenbank aus einem Snapshot wieder her.',
    ],
  },
  {
    version: '3.3.7',
    date: '2026-06-25',
    changes: [
      'Neu: Firmenlogos in der Firmenliste — wird automatisch via Clearbit geladen, Initialen als Fallback.',
      'Fix: Firmenprofil-Button im Bewerbungsmodal war nie klickbar (company_profile_id fehlte im Detail-Endpoint).',
      'Fix: "Firmendaten aktualisieren" war nach erstem Sync dauerhaft deaktiviert.',
    ],
  },
  {
    version: '3.3.6',
    date: '2026-06-25',
    changes: [
      'Fix: LI-Sync Session-Erkennung — nutzt jetzt /feed statt jobs-tracker als Check-URL, damit abgelaufene Sessions zuverlässig erkannt und neu eingeloggt werden.',
      'UX: 2FA-Dialog erklärt jetzt App-Bestätigung als primäre Option; Code-Eingabe bleibt als Fallback.',
    ],
  },
  {
    version: '3.3.5',
    date: '2026-06-25',
    changes: [
      'Fix: Status-Badge im Firmenprofil nutzt jetzt dieselbe StatusBadge-Komponente wie die Bewerbungsübersicht — identische Farben und Bezeichnungen.',
    ],
  },
  {
    version: '3.3.4',
    date: '2026-06-25',
    changes: [
      'Fix: LinkedIn-Button unten in der App war sichtbar — wird jetzt ausgeblendet, wenn er als reiner Dropdown-Trigger läuft.',
    ],
  },
  {
    version: '3.3.3',
    date: '2026-06-25',
    changes: [
      'Firmenprofil: Bewerbungsliste zeigt jetzt Rolle, Bewerbungsdatum und Status — Firmenname wurde entfernt (redundant).',
    ],
  },
  {
    version: '3.3.2',
    date: '2026-06-25',
    changes: [
      'UX: LinkedIn-Sync in den Sync-Dropdown integriert — kein separater Button mehr im Header.',
      'UX: Excel-Export, PDF-Export und Excel-Import in ein "Im/Export"-Dropdown zusammengefasst.',
    ],
  },
  {
    version: '3.3.1',
    date: '2026-06-25',
    changes: [
      'Firmensynchronisation von Analytics auf die Firmen-Seite verschoben — Sync-Button, Fortschrittsbalken und Fehler-Reset direkt in der Firmentabelle.',
    ],
  },
  {
    version: '3.3.0',
    date: '2026-06-25',
    changes: [
      'Neu: Firmen-Seite — alle Company Profiles tabellarisch mit Branche, Typ, Größe, Standort und Sync-Status.',
      'Neu: Firmenprofil-Modal mit allen KI-sync\'ten Daten (Beschreibung, Website, LinkedIn, Gründungsjahr, Mitarbeiterzahl) und verlinkten Bewerbungen.',
      'Firmennamen überall anklickbar: Tabelle, Kanban-Karten und Bewerbungsmodal öffnen jetzt das Firmenprofil.',
    ],
  },
  {
    version: '3.2.10',
    date: '2026-06-25',
    changes: [
      'Fix: LinkedIn-Sync erkennt abgelaufene Sessions korrekt — wenn LI auf die Startseite statt /login oder /authwall umleitet, wird jetzt trotzdem neu eingeloggt.',
    ],
  },
  {
    version: '3.2.9',
    date: '2026-06-25',
    changes: [
      'Fix: Ollama-Modell-Picker, Auto-Save und host.docker.internal-URL in die KI/API-Einstellungen (SettingsModal) portiert — war zuvor nur im standalone AiSettingsModal implementiert.',
      'Ollama: Modellauswahl als Chips (installiert) + Download-Liste mit Fortschrittsanzeige. Kein globaler Speichern-Button mehr.',
    ],
  },
  {
    version: '3.2.8',
    date: '2026-06-25',
    changes: [
      'UX: KI-Einstellungen speichern automatisch — Provider-Wechsel, Modell-Auswahl, Toggle und Textfelder (onBlur) triggern sofort einen Save.',
      'Kein globaler Speichern-Button mehr; API-Key hat einen eigenen OK-Button. Speicher-Status als Icon im Header.',
    ],
  },
  {
    version: '3.2.7',
    date: '2026-06-25',
    changes: [
      'Fix: Groq-API-Key nicht mehr als Fallback in Ollama-Test-Requests injiziert — Provider-Wechsel testet jetzt den richtigen Anbieter.',
      'Fix: Ollama-URL-Default ist jetzt host.docker.internal:11434 (statt localhost, das aus dem Container nicht erreichbar ist).',
      'UX: Speichern-Bestätigung zeigt gespeicherten Anbieter + Modell, Fehler werden sichtbar angezeigt.',
    ],
  },
  {
    version: '3.2.6',
    date: '2026-06-25',
    changes: [
      'Ollama-Modell-Picker: installierte Modelle als klickbare Chips, populäre Modelle mit Download-Button und Fortschrittsbalken.',
      'Neu: GET /api/settings/ollama/models (Modellliste) + GET /api/settings/ollama/pull (SSE-Stream für Download-Fortschritt).',
    ],
  },
  {
    version: '3.2.5',
    date: '2026-06-25',
    changes: [
      'Firmendaten-Sync jetzt via KI (statt LinkedIn-Scraping) — kein Login nötig, funktioniert mit jedem konfigurierten AI-Anbieter.',
      'Live-Fortschritt: Fortschrittsbalken und aktuell synchronisierte Firma werden während des Sync angezeigt (Polling alle 1,5 s).',
    ],
  },
  {
    version: '3.2.4',
    date: '2026-06-25',
    changes: [
      'Fix: Letztes Update zeigt jetzt immer das Datum des letzten Timeline-Eintrags — nicht mehr das Datum der letzten Bearbeitung.',
    ],
  },
  {
    version: '3.2.3',
    date: '2026-06-25',
    changes: [
      'Fix: Firmendaten-Sync — Browser-Flags (--no-sandbox), strukturbasierte LI-Firmenerkennung statt gehashter Klassen, Login-Fallback.',
      'Firmendaten-Sync: Lock-Reset vor jedem Run (kein "already running" mehr), "fehlgeschlagen zurücksetzen"-Button im Auswertungen-Tab.',
    ],
  },
  {
    version: '3.2.2',
    date: '2026-06-25',
    changes: [
      'Interview-Rate aus der Bewerbungsseite entfernt — steht jetzt im Auswertungen-Tab.',
    ],
  },
  {
    version: '3.2.1',
    date: '2026-06-25',
    changes: [
      'Backfill: Beim Containerstart werden für alle bestehenden Bewerbungen automatisch CompanyProfile-Einträge (pending) angelegt — Firmennamen werden dedupliziert.',
    ],
  },
  {
    version: '3.2.0',
    date: '2026-06-25',
    changes: [
      'Neu: Auswertungen-Tab — KPI-Kacheln, Conversion-Funnel, Pipeline-Donut, Quellen-Balken, HH-vs-Direkt-Vergleich, Bewerbungen über Zeit, Absagen nach Phase.',
      'Backend: GET /api/analytics/summary — berechnet alle KPIs, Funnel, Monatsverteilung und Firmenprofil-Sync-Status direkt aus der DB.',
      'Firmendaten-Sync: POST /api/sync/company/run — startet LinkedIn-Scraping für ausstehende CompanyProfile im Hintergrund (max. 10 pro Run).',
      'Auto-CompanyProfile: Beim Anlegen/Aktualisieren von Bewerbungen werden Firmennamen automatisch normalisiert und in company_profiles eingetragen (sync_status=pending).',
    ],
  },
  {
    version: '3.1.0',
    date: '2026-06-25',
    changes: [
      'Vorbereitung Auswertungen: Neue DB-Tabelle company_profiles (HQ, Branche, Unternehmenstyp, Mitarbeiterzahl, Gründungsjahr, LinkedIn-URL) für Background-Sync von Firmendaten.',
      'Applications erhalten company_profile_id und target_company_profile_id (bei HH-Bewerbungen) als FK.',
    ],
  },
  {
    version: '3.0.4',
    date: '2026-06-25',
    changes: [
      'Fix: Stellenbeschreibung LI — TreeWalker findet "About the job"/"Stellenbeschreibung"-Abschnitt direkt, kein Klassen-Matching mehr nötig.',
    ],
  },
  {
    version: '3.0.3',
    date: '2026-06-25',
    changes: [
      'Fix: Beschreibungsextraktor schließt Elemente mit Nav/Header/Footer-Kindknoten aus — verhindert dass Seiten-Chrome als Beschreibung zurückgegeben wird.',
    ],
  },
  {
    version: '3.0.2',
    date: '2026-06-25',
    changes: [
      'Fix: Stellenbeschreibung in Jobsuche — strukturbasierte DOM-Erkennung statt Klassenname (LI hasht alle CSS-Klassen). Findet den reichsten Inhaltsblock außerhalb von Nav/Header/Footer.',
    ],
  },
  {
    version: '3.0.1',
    date: '2026-06-25',
    changes: [
      'Fix: Stellenbeschreibung als HTML rendern — innerHTML statt innerText, dangerouslySetInnerHTML mit Prose-Styling im Frontend.',
    ],
  },
  {
    version: '3.0.0',
    date: '2026-06-25',
    changes: [
      'Neu: Jobsuche — eigener Tab zum Durchsuchen von Jobportalen direkt aus JobTracker',
      'LinkedIn-Integration: Suche direkt über die bestehende LI-Session, Ergebnisse mit Firma, Stelle, Ort und Easy-Apply-Kennzeichnung',
      'Weitere Portale (StepStone, Indeed, Xing, Experteer, Headhunter24, Jobware) per Klick im Browser öffnen — Suchanfrage wird automatisch übertragen',
      'Mehrere Ergebnisse auswählen und mit einem Klick als Anbahnung in den Jobtracker übernehmen — Duplikate werden erkannt und übersprungen',
      'Einstellungen › Jobportale: eigene Portale hinzufügen, bearbeiten und aktivieren/deaktivieren',
    ],
  },
  {
    version: '2.6.5',
    date: '2026-06-25',
    changes: [
      'Fix: Kanban-Board nutzt jetzt volle Viewport-Breite (außerhalb max-w-7xl) — Lanes werden nicht mehr abgeschnitten, horizontales Scrollen funktioniert über die ganze Bildschirmbreite.',
      'Fix: Generische Abteilungs-Mailadressen (career@, jobs@, recruiting@, bewerbung@, hr@ u.a.) werden nicht mehr als Kontakte angelegt und nicht an mehrere Bewerbungen angehängt.',
    ],
  },
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
