"""
AI tasks for intelligent event matching and classification.
All tasks return typed dicts; the caller decides what to persist.
"""
from __future__ import annotations
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
