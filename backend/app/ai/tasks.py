"""
AI tasks for intelligent event matching and classification.
All tasks return typed dicts; the caller decides what to persist.
"""
from __future__ import annotations
from typing import Optional
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


_ASSESS_SYSTEM = """\
Du bist ein erfahrener Karrierecoach. Du bewertest Bewerbungssituationen nüchtern und präzise.
Antworte ausschließlich als valides JSON-Objekt, kein Markdown, keine Erklärungen außerhalb des JSON.
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

# The response-language instruction is the one thing that must actually change per
# account — the German field labels above (Firma/Stelle/Status/…) stay as prompt
# scaffolding regardless, since LLMs handle a German-labeled data block fine even
# when told to answer in English.
_RESPONSE_LANGUAGE_NOTE = {
    "de": 'Schreibe "reasoning" und "next_step" auf Deutsch.',
    "en": 'Write "reasoning" and "next_step" in English.',
}


def _build_profile_block(cv_text: Optional[str], linkedin_text: Optional[str]) -> str:
    """Optional '=== BEWERBERPROFIL ===' prompt section — CV text (backend
    app/cv_extract.py) and/or cached LinkedIn profile text (routers/
    sync_linkedin.py's scrape_own_profile()), when available. Returns an
    empty string when neither is present, so the prompt looks exactly like
    it did before this data existed for users who haven't uploaded a CV or
    synced a LinkedIn profile yet."""
    parts = []
    if cv_text:
        parts.append(f"Lebenslauf (Auszug):\n{cv_text}")
    if linkedin_text:
        parts.append(f"LinkedIn-Profil (Auszug):\n{linkedin_text}")
    if not parts:
        return ""
    return "=== BEWERBERPROFIL ===\n" + "\n\n".join(parts) + "\n\n"


async def assess_application(
    db: Session, app, ui_language: str = "de",
    cv_text: Optional[str] = None, linkedin_text: Optional[str] = None,
) -> dict:
    """
    Generate AI assessment for a single application based on ALL available data.
    Returns: {"color": "green"|"yellow"|"red", "next_step": str}
    """
    from datetime import date as _date
    lang_note = _RESPONSE_LANGUAGE_NOTE.get(ui_language, _RESPONSE_LANGUAGE_NOTE["de"])
    profile_block = _build_profile_block(cv_text, linkedin_text)
    profile_reasoning_note = (
        "\n   - Falls oben ein Lebenslauf/LinkedIn-Profil vorhanden ist: beziehe ein, wie gut es zur Rolle passt"
        if profile_block else ""
    )
    firma = getattr(app, 'company_name_display', None) or app.firma
    status_label = _STATUS_LABELS.get(app.main_status, app.main_status)
    today = _date.today()

    # All events sorted chronologically (oldest first = narrative order)
    events = sorted(
        [e for e in (app.events or []) if e.datum],
        key=lambda e: e.datum,
    )

    # Computed facts (calculated in Python — no placeholders for the AI to guess)
    days_since_apply  = (today - app.datum_bewerbung).days if app.datum_bewerbung else None
    last_event_date   = events[-1].datum if events else None
    days_since_last   = (today - last_event_date).days if last_event_date else None

    # Build full timeline — ALL events, vollständiger Inhalt
    timeline_lines = []
    for e in events:
        age = (today - e.datum).days
        line = f"{e.datum.strftime('%d.%m.%Y')} (vor {age}d) [{e.typ}]"
        if e.autor:
            autor_short = e.autor.split('<')[0].strip().strip('"') or e.autor
            line += f" | von: {autor_short[:80]}"
        if e.titel:
            line += f"\n  Betreff: {e.titel}"
        if e.notiz and e.notiz.strip():
            line += f"\n  Inhalt: {e.notiz.strip()}"
        timeline_lines.append(line)
    timeline_text = "\n\n".join(timeline_lines) if timeline_lines else "(keine Ereignisse)"

    # Application metadata block
    meta_parts = [
        f"Firma: {firma}",
        f"Stelle: {app.rolle}",
        f"Status: {status_label}",
    ]
    if app.quelle:
        meta_parts.append(f"Quelle: {app.quelle}")
    if app.is_headhunter and app.zielfirma_bei_hh:
        meta_parts.append(f"Headhunter für: {app.zielfirma_bei_hh}")
    if days_since_apply is not None:
        meta_parts.append(f"Beworben: {app.datum_bewerbung.strftime('%d.%m.%Y')} (vor {days_since_apply} Tagen)")
    if days_since_last is not None:
        meta_parts.append(f"Letztes Ereignis: {last_event_date.strftime('%d.%m.%Y')} (vor {days_since_last} Tagen)")
    if app.kommentar:
        meta_parts.append(f"Kommentar: {app.kommentar[:300]}")
    gespraeche = [g for g in [app.gespraech_1, app.gespraech_2, app.gespraech_3, app.gespraech_4, app.gespraech_5] if g]
    for i, g in enumerate(gespraeche, 1):
        meta_parts.append(f"Gesprächsnotiz {i}: {g[:300]}")

    meta_text = "\n".join(meta_parts)

    prompt = f"""=== BEWERBUNG ===
{meta_text}

{profile_block}=== VOLLSTÄNDIGE TIMELINE (chronologisch) ===
{timeline_text}

=== HEUTE ===
{today.strftime('%d.%m.%Y')}

=== AUFGABE ===
Gib ein JSON-Objekt mit genau drei Feldern zurück:

1. "color" — Wie wahrscheinlich führt diese Bewerbung noch zu einem Angebot?
   - "green": hoch (>60%) — fortgeschrittener Prozess, mehrere Gespräche, positives Signal, Angebot/Verhandlung
   - "yellow": mittel (30–60%) — laufend, unklar, normale Wartezeit nach 1–2 Gesprächen
   - "red": niedrig (<30%) — keine Reaktion seit >3 Wochen, Ghosting, frühe Phase ohne Signal, Absage

2. "reasoning" — Warum diese Einschätzung? (2–3 Sätze)
   - Nenne konkrete Fakten aus der Timeline: Anzahl Gespräche, Tage seit letztem Kontakt, letzte Signale
   - Erkläre was für und was gegen eine Zusage spricht{profile_reasoning_note}
   - Keine Floskeln, nur faktenbezogene Begründung

3. "next_step" — Was soll der Bewerber konkret tun? (1–2 Sätze, Imperativ)
   STRIKT VERBOTEN:
   - Daten oder Deadlines erfinden die NICHT in der Timeline stehen
   - Wochentage nennen
   - Status-Labels wiederholen ("Warten auf Entscheidung")
   - E-Mail-Betreff wörtlich kopieren

{lang_note}

{{"color": "green"|"yellow"|"red", "reasoning": "...", "next_step": "..."}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _ASSESS_SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=300,
    )

    color = result.get("color")
    if color not in ("green", "yellow", "red"):
        color = "yellow"

    return {
        "color": color,
        "reasoning": result.get("reasoning") or "",
        "next_step": result.get("next_step") or "",
    }


async def assess_rejected_application(
    db: Session, app, ui_language: str = "de",
    cv_text: Optional[str] = None, linkedin_text: Optional[str] = None,
) -> dict:
    """
    Analyse a rejected application: find likely rejection reasons and derive
    optimization suggestions for future applications.
    Returns: {"color": "red", "reasoning": str, "next_step": str}
    """
    from datetime import date as _date
    lang_note = _RESPONSE_LANGUAGE_NOTE.get(ui_language, _RESPONSE_LANGUAGE_NOTE["de"])
    profile_block = _build_profile_block(cv_text, linkedin_text)
    profile_next_step_note = (
        "\n   - Falls oben ein Lebenslauf/LinkedIn-Profil vorhanden ist: beziehe ein, ob das Profil zur Rolle passte"
        if profile_block else ""
    )
    firma = getattr(app, 'company_name_display', None) or app.firma
    status_label = _STATUS_LABELS.get(app.main_status, app.main_status)
    today = _date.today()

    events = sorted(
        [e for e in (app.events or []) if e.datum],
        key=lambda e: e.datum,
    )

    timeline_lines = []
    for e in events:
        age = (today - e.datum).days
        line = f"{e.datum.strftime('%d.%m.%Y')} (vor {age}d) [{e.typ}]"
        if e.autor:
            autor_short = e.autor.split('<')[0].strip().strip('"') or e.autor
            line += f" | von: {autor_short[:80]}"
        if e.titel:
            line += f"\n  Betreff: {e.titel}"
        if e.notiz and e.notiz.strip():
            line += f"\n  Inhalt: {e.notiz.strip()}"
        timeline_lines.append(line)
    timeline_text = "\n\n".join(timeline_lines) if timeline_lines else "(keine Ereignisse)"

    meta_parts = [
        f"Firma: {firma}",
        f"Stelle: {app.rolle}",
        f"Status: {status_label}",
    ]
    if app.datum_bewerbung:
        meta_parts.append(f"Beworben: {app.datum_bewerbung.strftime('%d.%m.%Y')}")
    if app.kommentar:
        meta_parts.append(f"Kommentar: {app.kommentar[:300]}")
    gespraeche = [g for g in [app.gespraech_1, app.gespraech_2, app.gespraech_3, app.gespraech_4, app.gespraech_5] if g]
    for i, g in enumerate(gespraeche, 1):
        meta_parts.append(f"Gesprächsnotiz {i}: {g[:300]}")
    meta_text = "\n".join(meta_parts)

    prompt = f"""=== ABGESAGTE BEWERBUNG ===
{meta_text}

{profile_block}=== VOLLSTÄNDIGE TIMELINE (chronologisch) ===
{timeline_text}

=== HEUTE ===
{today.strftime('%d.%m.%Y')}

=== AUFGABE ===
Diese Bewerbung endete mit einer Absage. Analysiere die Timeline und gib ein JSON-Objekt mit drei Feldern zurück:

1. "color": immer "red"

2. "reasoning" — Wahrscheinliche Absagegründe (2–3 Sätze):
   - Leite die Gründe aus der Timeline ab (Zeitpunkt der Absage, wie weit der Prozess kam, Signale aus E-Mails)
   - Unterscheide: Prozesstiefe (frühe/späte Absage), mögliche inhaltliche Gründe, externe Faktoren
   - Wenn keine klaren Gründe erkennbar: sage das ehrlich

3. "next_step" — Konkrete Optimierungsvorschläge für zukünftige Bewerbungen (2–3 Sätze):
   - Was hätte anders laufen können? Was kann der Bewerber beim nächsten Mal besser machen?
   - Bezug auf den spezifischen Fall (Branche, Rolle, Prozess){profile_next_step_note}

{lang_note}

{{"color": "red", "reasoning": "...", "next_step": "..."}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _ASSESS_SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=400,
    )

    return {
        "color": "red",
        "reasoning": result.get("reasoning") or "",
        "next_step": result.get("next_step") or "",
    }


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
