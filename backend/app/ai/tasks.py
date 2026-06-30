"""
AI tasks for intelligent event matching and classification.
All tasks return typed dicts; the caller decides what to persist.
"""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.ai.provider import complete, AINotConfigured, AIRateLimited

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
Du bist ein erfahrener Karrierecoach. Du bewertest Bewerbungssituationen nüchtern und konkret.
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

_RELEVANT_EVENT_TYPES = {"bewerbung", "gespräch", "interview", "status", "notiz", "email", "anruf", "angebot", "absage"}


async def assess_application(db: Session, app) -> dict:
    """
    Generate AI assessment for a single application.
    Returns: {"color": "green"|"yellow"|"red", "next_step": str}
    """
    from datetime import date as _date
    firma = getattr(app, 'company_name_display', None) or app.firma
    status_label = _STATUS_LABELS.get(app.main_status, app.main_status)
    today = _date.today()

    # Only process relevant event types, sorted newest first, skip file events
    all_events = sorted(
        [e for e in (app.events or []) if e.datum and e.typ not in ("file",)],
        key=lambda e: e.datum,
        reverse=True,
    )

    # Count interviews (gespräch/status events) for process depth
    interview_events = [e for e in all_events if e.typ in ("gespräch", "interview") or
                        (e.typ == "status" and e.titel and "gespräch" in e.titel.lower())]
    interview_count = len(interview_events)

    # Last contact date (most recent event with a date)
    last_event_date = all_events[0].datum if all_events else None
    days_since_last_contact = (today - last_event_date).days if last_event_date else None

    days_since_apply = (today - app.datum_bewerbung).days if app.datum_bewerbung else None

    # Build timeline — max 12 most recent relevant events, with content
    timeline_lines = []
    for e in all_events[:12]:
        age = (today - e.datum).days
        line = f"  {e.datum.strftime('%d.%m.%Y')} (vor {age}d): [{e.typ}]"
        if e.titel:
            line += f" {e.titel[:80]}"
        if e.notiz and e.notiz.strip():
            line += f"\n    → {e.notiz.strip()[:250]}"
        timeline_lines.append(line)
    timeline = "\n".join(timeline_lines) if timeline_lines else "  (keine Ereignisse)"

    # Key facts summary for the model
    facts = []
    if days_since_apply is not None:
        facts.append(f"Beworben vor {days_since_apply} Tagen ({app.datum_bewerbung.strftime('%d.%m.%Y') if app.datum_bewerbung else '?'})")
    if interview_count > 0:
        facts.append(f"{interview_count} Gespräch{'e' if interview_count > 1 else ''} stattgefunden")
    if days_since_last_contact is not None:
        facts.append(f"Letzter Kontakt vor {days_since_last_contact} Tagen ({last_event_date.strftime('%d.%m.%Y') if last_event_date else '?'})")
    if app.is_headhunter and app.zielfirma_bei_hh:
        facts.append(f"Headhunter-Bewerbung für: {app.zielfirma_bei_hh}")

    prompt = f"""Bewerbungssituation analysieren:

Firma: {firma}
Stelle: {app.rolle}
Status: {status_label}
{chr(10).join(facts)}

Timeline (neueste zuerst):
{timeline}

Aufgabe:
1. Schätze die WAHRSCHEINLICHKEIT ein, dass diese Bewerbung zu einem Angebot führt.
2. Formuliere den NÄCHSTEN SINNVOLLEN SCHRITT — konkret, situationsbezogen, handlungsorientiert.

color-Bedeutung (Wahrscheinlichkeit für ein Angebot):
- "green": Hoch (>60%) — fortgeschrittener Prozess, positive Signale, mehrere Gespräche erfolgreich absolviert, Angebot/Vertragsverhandlung
- "yellow": Mittel (30-60%) — laufender Prozess, normale Wartezeit, unklar
- "red": Niedrig (<30%) — keine Reaktion seit >3 Wochen, Ghosting-Muster, frühe Phase ohne Signale, Absage

next_step: 1-2 konkrete Sätze auf Deutsch. KEINE Platzhalter wie "X Tage" — berechne echte Zahlen aus der Timeline.
Beziehe dich auf die tatsächliche Situation (z.B. Anzahl Gespräche, letztes Ereignis, Status).

{{
  "color": "green"|"yellow"|"red",
  "next_step": "<situationsspezifischer nächster Schritt>"
}}"""

    result = await complete(
        db,
        [{"role": "system", "content": _ASSESS_SYSTEM}, {"role": "user", "content": prompt}],
        json_mode=True,
        max_tokens=250,
    )

    color = result.get("color")
    if color not in ("green", "yellow", "red"):
        color = "yellow"

    return {"color": color, "next_step": result.get("next_step") or ""}
