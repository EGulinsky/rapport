"""
AI tasks for intelligent event matching and classification.
All tasks return typed dicts; the caller decides what to persist.
"""
from __future__ import annotations
from datetime import date
from sqlalchemy.orm import Session
from app.ai.provider import complete, AINotConfigured, AIRateLimited
from app.i18n_strings import resolve_ui_language  # noqa: F401 — re-exported for existing call sites/tests

_SYSTEM = """\
Du bist ein KI-Assistent für einen aktiven Bewerber.
Du analysierst Rohdaten (E-Mails, Kalendereinträge, Notizen, Anrufe) und ordnest sie
den bekannten Bewerbungen zu. Antworte ausschließlich als valides JSON-Objekt, kein Markdown.
Datum immer als ISO-Format YYYY-MM-DD. Fehlende Werte als null.
"""

_STATUS_HINT = """\
Erlaubte main_status-Werte: prospecting, applied, hr, fb, waiting, negotiating, signed, rejected
Erlaubte sub_status-Werte:  1_scheduled, 1_done, 2_scheduled, 2_done, 3_scheduled, 3_done, null
"""

_EVENT_TYPES = (
    "interview_scheduled | interview_done | rejection | offer | "
    "callback | note | application | other"
)


async def match_and_classify(
    db: Session,
    source: str,
    raw_text: str,
    applications: list[dict],
    hint_apps: list[dict] | None = None,
) -> dict:
    """
    Analyse raw text from a data source and return structured match result.

    hint_apps: pre-identified candidate applications (found via firm-name search).
               When provided, the AI is told these are the likely matches.

    Returns:
        application_id  – int or null
        confidence      – float 0–1
        event_type      – one of _EVENT_TYPES
        datum           – YYYY-MM-DD or null
        titel           – short title ≤ 60 chars
        extract         – relevant snippet ≤ 200 chars
        suggested_main_status  – str or null
        suggested_sub_status   – str or null
    """
    def _fmt_app(a: dict) -> str:
        extra = ""
        if a.get("zielfirma"):
            extra += f" (Zielfirma: {a['zielfirma']})"
        if a.get("besetzt_von"):
            extra += f" (besetzt von: {a['besetzt_von']})"
        return f"  - ID {a['id']}: {a['firma']} | {a['rolle']}{extra}"

    app_list = "\n".join(_fmt_app(a) for a in applications)

    hint_block = ""
    if hint_apps:
        hint_lines = "\n".join(_fmt_app(a) for a in hint_apps)
        hint_block = (
            f"\nHINWEIS: Dieser Eintrag wurde durch Suche nach dem Firmennamen gefunden. "
            f"Wahrscheinliche Bewerbung(en):\n{hint_lines}\n"
            f"Bevorzuge diese Bewerbungen bei der Zuordnung und setze confidence entsprechend hoch (≥0.75).\n"
        )

    prompt = f"""\
Quelle: {source}
{hint_block}
Inhalt (max. 2000 Zeichen):
---
{raw_text[:2000]}
---

Alle bekannten Bewerbungen:
{app_list}

{_STATUS_HINT}

Gib zurück:
{{
  "application_id": <int|null>,
  "confidence": <0.0–1.0>,
  "event_type": "<{_EVENT_TYPES}>",
  "datum": "<YYYY-MM-DD|null>",
  "titel": "<max 60 Zeichen>",
  "extract": "<PFLICHT wenn relevant: 1–2 prägnante Sätze, was der Inhalt konkret besagt — niemals null>",
  "suggested_main_status": <str|null>,
  "suggested_sub_status": <str|null>
}}"""

    return await complete(
        db,
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=512,
    )


async def classify_for_app(
    db: Session,
    source: str,
    raw_text: str,
    app: dict,
) -> dict:
    """
    Decide whether a single item is relevant to ONE specific application and classify it.
    Much more accurate than match_and_classify because there's no competing application list.

    Returns same schema as match_and_classify, but application_id is pre-filled when relevant.
    """
    zielfirma = app.get("zielfirma")
    if zielfirma:
        bewerbung_desc = (
            f"Headhunter: {app['firma']}\n"
            f"Zielunternehmen: {zielfirma}\n"
            f"Stelle: {app['rolle']}"
        )
        relevance_rule = (
            f"WICHTIG: Dieser Headhunter betreut mehrere Vakanzen. "
            f"Relevant ist NUR Inhalt, der explizit die Stelle '{app['rolle']}' "
            f"ODER das Unternehmen '{zielfirma}' betrifft. "
            f"Mails über andere Vakanzen des Headhunters → relevant=false."
        )
    else:
        bewerbung_desc = f"Unternehmen: {app['firma']}\nStelle: {app['rolle']}"
        relevance_rule = f"Relevant ist nur Inhalt, der diese konkrete Stelle bei {app['firma']} betrifft."

    prompt = f"""\
Quelle: {source}

Zu prüfende Bewerbung (ID {app['id']}):
{bewerbung_desc}

{relevance_rule}

Inhalt (max. 2000 Zeichen):
---
{raw_text[:2000]}
---

{_STATUS_HINT}

Antworte:
{{
  "relevant": <true|false>,
  "confidence": <0.0–1.0>,
  "event_type": "<{_EVENT_TYPES}>",
  "datum": "<YYYY-MM-DD|null>",
  "titel": "<max 60 Zeichen>",
  "extract": "<PFLICHT wenn relevant=true: 1–2 prägnante Sätze, was der Inhalt konkret besagt — niemals null>",
  "suggested_main_status": <str|null>,
  "suggested_sub_status": <str|null>
}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=512,
    )
    if not result.get("relevant", True):
        result["confidence"] = 0.0
        result["application_id"] = None
    else:
        result["application_id"] = app["id"]
    return result


BATCH_SIZE = 8


async def classify_batch_for_app(
    db: Session,
    source: str,
    items: list[dict],  # each: {"id": str, "raw": str}
    app: dict,
) -> list[dict]:
    """
    Classify multiple items in one AI call instead of one call per item.
    Returns results in same order (same schema as classify_for_app).
    Falls back to individual classify_for_app calls if the batch response is malformed.
    """
    if not items:
        return []
    if len(items) == 1:
        return [await classify_for_app(db, source, items[0]["raw"], app)]

    zielfirma = app.get("zielfirma")
    if zielfirma:
        bewerbung_desc = (
            f"Headhunter: {app['firma']}\n"
            f"Zielunternehmen: {zielfirma}\n"
            f"Stelle: {app['rolle']}"
        )
        relevance_rule = (
            f"Relevant ist NUR Inhalt der explizit die Stelle '{app['rolle']}' "
            f"ODER das Unternehmen '{zielfirma}' betrifft. "
            f"Mails zu anderen Vakanzen des Headhunters → relevant=false."
        )
    else:
        bewerbung_desc = f"Unternehmen: {app['firma']}\nStelle: {app['rolle']}"
        relevance_rule = f"Relevant ist nur Inhalt der diese konkrete Stelle bei {app['firma']} betrifft."

    n = len(items)
    entries = "\n\n".join(
        f"[{i + 1}]\n{item['raw'][:800]}" for i, item in enumerate(items)
    )

    prompt = f"""\
Quelle: {source}

Bewerbung (ID {app['id']}):
{bewerbung_desc}

{relevance_rule}

{_STATUS_HINT}

Klassifiziere folgende {n} Einträge. Irrelevante Einträge: relevant=false, confidence niedrig, restliche Felder null.

{entries}

Antworte als JSON-Objekt mit "items"-Array — genau {n} Objekte in gleicher Reihenfolge:
{{
  "items": [
    {{"relevant": <bool>, "confidence": <0.0–1.0>, "event_type": "<{_EVENT_TYPES}|null>", "datum": "<YYYY-MM-DD|null>", "titel": "<max 60 Zeichen|null>", "extract": "<1–2 Sätze wenn relevant, sonst null>", "suggested_main_status": <str|null>, "suggested_sub_status": <str|null>}},
    ...
  ]
}}"""

    async def _fallback() -> list[dict]:
        results = []
        for item in items:
            try:
                r = await classify_for_app(db, source, item["raw"], app)
            except (AINotConfigured, AIRateLimited):
                raise
            except Exception:
                r = {"relevant": False, "confidence": 0.0, "application_id": None}
            results.append(r)
        return results

    try:
        response = await complete(
            db,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
            json_mode=True,
            max_tokens=min(300 * n, 4096),
        )
        batch_results = response.get("items", [])
        if len(batch_results) != n:
            return await _fallback()
        results = []
        for item, result in zip(items, batch_results):
            if not result.get("relevant", True):
                result["confidence"] = 0.0
                result["application_id"] = None
            else:
                result["application_id"] = app["id"]
            results.append(result)
        return results
    except (AINotConfigured, AIRateLimited):
        raise
    except Exception:
        return await _fallback()


async def test_connection(db: Session) -> str:
    """Minimal round-trip to verify the provider is reachable."""
    result = await complete(
        db,
        [{"role": "user", "content": 'Antworte mit dem JSON {"ok": true}'}],
        json_mode=True,
        max_tokens=32,
    )
    return "ok" if result.get("ok") else f"Unerwartete Antwort: {result}"


_EXTRACT_SYSTEM = """\
Du bist ein KI-Assistent für einen aktiven Bewerber. Du liest den Text einer
LinkedIn-Stellenanzeige (kopiert von der Jobseite) und extrahierst strukturierte
Felder für eine neue Bewerbung. Antworte ausschließlich als valides JSON-Objekt,
kein Markdown. Fehlende Werte als null bzw. leerer String.
"""


async def extract_application_from_text(db: Session, raw_text: str) -> dict:
    """
    Parse a pasted LinkedIn job posting (or similar free-text job ad) into
    structured application fields for the "new application" form.

    Returns:
        firma            – Firmenname (Arbeitgeber, nicht Personalvermittlung)
        rolle             – Jobtitel
        quelle            – i.d.R. "LinkedIn"
        is_headhunter     – true wenn über Personalvermittlung/Headhunter ausgeschrieben
        zielfirma_bei_hh  – Zielfirma/Auftraggeber falls is_headhunter, sonst null
        kommentar         – 1–2 Sätze Kurzbeschreibung (Standort, Seniorität, Besonderheiten)
    """
    prompt = f"""\
Text der Stellenanzeige (von LinkedIn kopiert):
---
{raw_text[:4000]}
---

Prüfe zuerst, ob die Anzeige von einer Personalvermittlung/einem Headhunter
geschaltet wurde statt direkt vom Arbeitgeber. Anzeichen dafür:
- Formulierungen wie "im Auftrag von/für unseren Kunden", "on behalf of our client",
  "for our client", "for a leading company", "wir suchen für einen Kunden/Mandanten"
- Die anzeigenschaltende Firma trägt Begriffe wie "Personalberatung", "Executive Search",
  "Recruiting", "Headhunter", "Search & Selection", "HR Consulting", "Talent Partners"
  im eigenen Namen
- Der eigentliche Arbeitgeber wird nur vage/anonymisiert beschrieben
  (z.B. "ein börsennotierter Technologiekonzern", "ein führendes Unternehmen der Branche X")

Setze in diesem Fall is_headhunter=true und fülle zielfirma_bei_hh mit allem,
was über den Auftraggeber bekannt ist — auch wenn nur eine anonymisierte
Beschreibung vorliegt (z.B. "Börsennotierter Technologiekonzern, Branche
Maschinenbau" statt null). Lass zielfirma_bei_hh nur dann leer, wenn der
Text wirklich keinerlei Hinweis auf den Auftraggeber enthält.

Extrahiere:
{{
  "firma": "<Firmenname der anzeigenschaltenden Firma — bei Headhunter-Anzeige der Headhunter/die Personalberatung selbst, sonst der direkte Arbeitgeber>",
  "rolle": "<Jobtitel>",
  "quelle": "LinkedIn",
  "is_headhunter": <true|false>,
  "zielfirma_bei_hh": "<was über den Auftraggeber bekannt ist, ggf. anonymisierte Beschreibung|null>",
  "kommentar": "<kurze Zusammenfassung, max 2 Sätze — NICHT die Auftraggeber-Beschreibung wiederholen|null>"
}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _EXTRACT_SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=400,
    )

    return {
        "firma": result.get("firma") or "",
        "rolle": result.get("rolle") or "",
        "quelle": result.get("quelle") or "LinkedIn",
        "is_headhunter": bool(result.get("is_headhunter") or False),
        "zielfirma_bei_hh": result.get("zielfirma_bei_hh") or None,
        "kommentar": result.get("kommentar") or None,
    }


# Match score / success probability (see routers/applications.py::score_application()).
# Same additive-block/language-note pattern the (now removed) traffic-light
# assessment used — not resurrecting its color/next-step semantics, just this
# well-tested shape for building the prompt.

_SCORE_LANGUAGE_NOTE = {
    "de": 'Schreibe "reasoning" auf Deutsch.',
    "en": 'Write "reasoning" in English.',
}

_MATCH_SCORE_SYSTEM = """\
Du bist ein erfahrener, sehr anspruchsvoller Recruiting-Verantwortlicher in einem \
Bewerbermarkt zugunsten der Firma (viele gut qualifizierte Bewerber pro Stelle). Du \
bewertest kritisch, wie gut ein Bewerberprofil zu einer Stellenanzeige passt — ohne \
Wohlwollen und ohne im Zweifel zugunsten des Bewerbers zu entscheiden. Antworte \
ausschließlich als valides JSON-Objekt, kein Markdown, keine Erklärungen außerhalb \
des JSON.
"""

_SUCCESS_PROBABILITY_SYSTEM = """\
Du bist ein erfahrener Karrierecoach. Du schätzt, wie wahrscheinlich eine Bewerbung \
noch zu einem Angebot führt. Antworte ausschließlich als valides JSON-Objekt, \
kein Markdown, keine Erklärungen außerhalb des JSON.
"""

_STATUS_LABELS = {
    "prospecting": "Anbahnung",
    "applied": "Beworben",
    "hr": "Gespräch HR/HH",
    "fb": "Gespräch FB",
    "waiting": "Warten auf Entscheidung",
    "negotiating": "Angebotsverhandlung",
    "signed": "Unterschrift",
    "rejected": "Absage",
}


def _build_profile_block(cv_text: str | None, linkedin_text: str | None) -> str:
    """Optional '=== BEWERBERPROFIL ===' prompt section — CV text (app/
    cv_extract.py) and/or cached LinkedIn profile text (routers/
    sync_linkedin.py's scrape_own_profile()), when available. Empty string
    when neither is present."""
    parts = []
    if cv_text:
        parts.append(f"Lebenslauf (Auszug):\n{cv_text}")
    if linkedin_text:
        parts.append(f"LinkedIn-Profil (Auszug):\n{linkedin_text}")
    if not parts:
        return ""
    return "=== BEWERBERPROFIL ===\n" + "\n\n".join(parts) + "\n\n"


def _clamp_score(value, default: int = 0) -> int:
    """Defensively coerces an LLM-controlled numeric field to an int 0-100 —
    never trust the model to actually respect the requested range/type."""
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _build_jd_block(jd_texts: list[dict]) -> str:
    """'=== STELLENANZEIGE(N) ===' block — one or more candidate documents
    (an application's file-type attachments, or a scraped LinkedIn job
    posting as fallback — see ai/jd_resolve.py), labeled by filename. There's
    deliberately no code-side heuristic for which one is "the" job
    description when several are attached — the model judges relevance
    itself from the filenames, firma/rolle context, and content."""
    if not jd_texts:
        return ""
    parts = [f"[{jd['filename']}]\n{jd['text']}" for jd in jd_texts]
    return "=== STELLENANZEIGE(N) ===\n" + "\n\n".join(parts) + "\n\n"


def _build_activity_stats_block(app) -> str:
    """'=== KONTAKTHÄUFIGKEIT & -RICHTUNG ===' block for compute_success_probability —
    a code-computed summary of contact frequency, who initiates contact (Event.
    mail_direction), and (if set) the known candidate count, so the model doesn't
    have to infer these purely from the free-text timeline."""
    events = [e for e in app.events if e.datum]
    received = sum(1 for e in events if e.mail_direction == "received")
    sent = sum(1 for e in events if e.mail_direction == "sent")
    dated_count = len(events)
    contact_count = len(app.contacts)
    last = max((e.datum for e in events), default=None)
    days_since_last = (date.today() - last).days if last else None

    lines = [
        f"Anzahl Ereignisse gesamt: {dated_count}",
        f"Anzahl verknüpfter Kontaktpersonen: {contact_count}",
    ]
    if received or sent:
        direction_note = ""
        if received > sent:
            direction_note = "  (Firma meldet sich von sich aus)"
        elif sent > received:
            direction_note = "  (Kontakt geht überwiegend vom Bewerber aus)"
        lines.append(f"E-Mails von der Firma erhalten: {received} · E-Mails selbst gesendet: {sent}{direction_note}")
    if days_since_last is not None:
        lines.append(f"Letzte Aktivität vor {days_since_last} Tagen")
    bewerberzahl = getattr(app, "bewerberzahl", None)
    if bewerberzahl:
        lines.append(f"Bekannte Bewerberzahl (Momentaufnahme bei Veröffentlichung): {bewerberzahl}")

    return "=== KONTAKTHÄUFIGKEIT & -RICHTUNG ===\n" + "\n".join(lines) + "\n\n"


def _build_history_block(stats: dict | None) -> str:
    """'=== HISTORISCHE VERGLEICHSDATEN ===' block for compute_success_probability —
    see ai/historical_outcomes.py::compute_stage_outcomes()."""
    if not stats:
        return ""
    return (
        f"=== HISTORISCHE VERGLEICHSDATEN ===\n"
        f"Von {stats['total']} bisherigen Bewerbungen, die mindestens die Phase "
        f"\"{stats['stage_label']}\" erreicht haben, endeten {stats['signed']} mit einer "
        f"Zusage und {stats['rejected']} mit einer Absage.\n\n"
    )


def _build_feedback_block(entries: list[str]) -> str:
    """'=== HINWEISE DES BEWERBERS ZU FRÜHEREN EINSCHÄTZUNGEN ===' block — an
    append-only log of user-authored notes (models.ApplicationFeedback, added
    via rapportGPT's add_assessment_feedback tool, ai/chat.py), fed into both
    compute_match_score() and compute_success_probability() since a correction
    might target either assessment."""
    if not entries:
        return ""
    numbered = "\n".join(f"- {e}" for e in entries)
    return "=== HINWEISE DES BEWERBERS ZU FRÜHEREN EINSCHÄTZUNGEN ===\n" + numbered + "\n\n"


async def compute_match_score(
    db: Session,
    firma: str,
    rolle: str,
    profile_block: str,
    jd_texts: list[dict],
    feedback_entries: list[str] | None = None,
    ui_language: str = "de",
) -> dict:
    """How well does the applicant's profile (CV/LinkedIn, via profile_block)
    match the job's requirements (jd_texts)? Returns
    {"match_score": int 0-100, "reasoning": str}."""
    lang_note = _SCORE_LANGUAGE_NOTE.get(ui_language, _SCORE_LANGUAGE_NOTE["de"])
    jd_block = _build_jd_block(jd_texts)
    feedback_block = _build_feedback_block(feedback_entries or [])

    prompt = f"""=== BEWERBUNG ===
Firma: {firma}
Stelle: {rolle}

{profile_block}{jd_block}=== AUFGABE ===
Gib ein JSON-Objekt mit genau zwei Feldern zurück:

1. "match_score" — Wie gut passt das Bewerberprofil zu den Anforderungen der Stelle? \
Eine Zahl von 0 (kein erkennbarer Zusammenhang) bis 100 (nahezu perfekte Übereinstimmung).
   - Falls oben keine Stellenanzeige vorhanden ist: bewerte konservativ allein anhand von \
Firma/Stelle-Name, ohne Details zu erfinden.
   - Falls oben kein Bewerberprofil vorhanden ist: bewerte konservativ, ohne Qualifikationen zu erfinden.
   - Sei streng: Ziehe für jede fehlende oder nur teilweise erfüllte Kernanforderung \
(z.B. Jahre Erfahrung, konkrete Technologie/Zertifizierung, Ausbildungsabschluss, \
Sprachniveau) spürbar Punkte ab. Ein Wert über 80 ist nur gerechtfertigt, wenn \
praktisch alle zentralen Anforderungen erkennbar erfüllt sind — reine Überschneidung \
bei Soft Skills oder allgemeiner Berufserfahrung reicht nicht.

2. "reasoning" — Warum diese Einschätzung? (2-3 Sätze, konkrete Übereinstimmungen und Lücken benennen, \
keine Floskeln)

{feedback_block}{lang_note}

{{"match_score": <0-100>, "reasoning": "..."}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _MATCH_SCORE_SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=400,
    )

    return {
        "match_score": _clamp_score(result.get("match_score")),
        "reasoning": result.get("reasoning") or "",
    }


async def compute_success_probability(
    db: Session,
    firma: str,
    rolle: str,
    main_status: str,
    sub_status: str | None,
    match_score: int,
    match_reasoning: str,
    timeline_text: str,
    ghosting: bool,
    activity_stats_block: str = "",
    history_block: str = "",
    feedback_entries: list[str] | None = None,
    ui_language: str = "de",
) -> dict:
    """How likely is this application to still result in an offer? Goes beyond
    raw activity/progress: also weighs contact frequency and who initiates
    contact (activity_stats_block, see _build_activity_stats_block()), and how
    comparable past applications actually turned out (history_block, see
    ai/historical_outcomes.py). Returns {"success_probability": int 0-100,
    "reasoning": str}."""
    lang_note = _SCORE_LANGUAGE_NOTE.get(ui_language, _SCORE_LANGUAGE_NOTE["de"])
    status_label = _STATUS_LABELS.get(main_status, main_status)
    ghosting_note = "\nHinweis: Diese Bewerbung gilt aktuell als Ghosting (lange keine echte Aktivität)." if ghosting else ""
    feedback_block = _build_feedback_block(feedback_entries or [])

    prompt = f"""=== BEWERBUNG ===
Firma: {firma}
Stelle: {rolle}
Status: {status_label}{f" ({sub_status})" if sub_status else ""}{ghosting_note}

=== MATCH-SCORE ===
{match_score}/100 — {match_reasoning}

=== VOLLSTÄNDIGE TIMELINE (chronologisch) ===
{timeline_text}

{activity_stats_block}{history_block}{feedback_block}=== AUFGABE ===
Gib ein JSON-Objekt mit genau zwei Feldern zurück:

1. "success_probability" — Wie wahrscheinlich führt diese Bewerbung noch zu einem Angebot? \
Eine Zahl von 0 (praktisch ausgeschlossen) bis 100 (so gut wie sicher). Berücksichtige den \
Match-Score, den bisherigen Gesprächsverlauf, die Kontakthäufigkeit und -richtung, die bekannte \
Bewerberzahl (falls vorhanden), sowie die historischen Vergleichsdaten ähnlich weit fortgeschrittener \
bisheriger Bewerbungen — nicht nur den reinen Zeitverlauf/die Aktivität.

2. "reasoning" — Warum diese Einschätzung? (2-3 Sätze, konkrete Fakten aus Match-Score und Timeline nennen, \
keine Floskeln)

{lang_note}

{{"success_probability": <0-100>, "reasoning": "..."}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _SUCCESS_PROBABILITY_SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=400,
    )

    return {
        "success_probability": _clamp_score(result.get("success_probability")),
        "reasoning": result.get("reasoning") or "",
    }
