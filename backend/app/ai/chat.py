"""
rapportGPT — a tool-calling chat assistant with access to the user's own
application/contact/company data. See app/ai/provider.py::complete_with_tools()
for the underlying litellm plumbing this builds on.
"""
import json
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app import models
from app.ai.provider import complete_with_tools
from app.i18n_strings import resolve_ui_language
from app.logger import get_logger
from app.routers.companies import build_company_detail

log = get_logger("ai", source="chat")

MAX_TOOL_ITERATIONS = 6
HISTORY_WINDOW_MESSAGES = 20  # last N persisted rows sent as model context; full history still shown in the UI

_LANGUAGE_NAMES = {"de": "German", "en": "English"}

_SYSTEM_PROMPT = """\
You are rapportGPT, an assistant embedded in "rapport", the user's job-application tracker. \
You have tool access to the user's own application, contact, and company data — use it whenever \
a question needs facts you don't already have; never invent company names, dates, statuses, or numbers.

Today's date is {today}.

Guidelines:
- Call list_applications first for broad questions, then get_application_detail for the specific \
application(s) that matter.
- Call get_company_detail for company background (industry, size, etc.), not just the name you already know.
- Call get_user_profile at most once per conversation, only when the user's own background (CV/LinkedIn) \
is relevant (e.g. "should I apply", "how do I compare").
- If a tool returns an error (e.g. application not found, or several company matches), say so plainly and \
ask a clarifying question instead of guessing.
- Answer only in {language_name}, regardless of the language of any retrieved data.
- Be concise and concrete — cite specific facts (dates, counts, names) from tool results.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_applications",
            "description": "List the user's job applications in compact form (no timeline/contacts). Use this first to find application ids, then call get_application_detail for one specific application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["prospecting", "applied", "hr", "fb", "waiting", "negotiating", "signed", "rejected"],
                        "description": "Filter by main_status. Omit to return all statuses.",
                    },
                    "company_name_contains": {
                        "type": "string",
                        "description": "Case-insensitive substring filter on the company name.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_application_detail",
            "description": "Get full detail for one application: metadata, the complete chronological event timeline, linked contacts, and employer company background. Use after list_applications to look up a specific application by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {"type": "integer", "description": "The application's id, from list_applications."},
                },
                "required": ["application_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_detail",
            "description": "Get background info about a company: industry, size, HQ, website, description, subsidiaries/parent, other applications and contacts at this company.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer", "description": "Preferred if already known (e.g. from get_application_detail)."},
                    "company_name": {"type": "string", "description": "Company name to search for if the id isn't known."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Get the user's own background: name, cached CV text, cached LinkedIn profile text. Use when a question needs the user's own qualifications (e.g. fit for a role, comparison to a job posting).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _build_timeline_text(events: list) -> str:
    """Same chronological, full-content timeline format used by the (now
    removed) per-application assessment feature — kept here since it's a
    well-tested, readable shape for feeding an LLM an application's history."""
    today = date.today()
    ordered = sorted([e for e in events if e.datum], key=lambda e: e.datum)
    lines = []
    for e in ordered:
        age = (today - e.datum).days
        line = f"{e.datum.strftime('%d.%m.%Y')} (vor {age}d) [{e.typ}]"
        if e.autor:
            autor_short = e.autor.split('<')[0].strip().strip('"') or e.autor
            line += f" | von: {autor_short[:80]}"
        if e.titel:
            line += f"\n  Betreff: {e.titel}"
        if e.notiz and e.notiz.strip():
            line += f"\n  Inhalt: {e.notiz.strip()}"
        lines.append(line)
    return "\n\n".join(lines) if lines else "(keine Ereignisse)"


def _tool_list_applications(db: Session, args: dict) -> list[dict]:
    q = db.query(models.Application)
    status = args.get("status")
    if status:
        q = q.filter(models.Application.main_status == status)
    name_contains = args.get("company_name_contains")
    if name_contains:
        q = q.filter(models.Application.firma.ilike(f"%{name_contains}%"))
    apps = q.all()
    out = []
    for a in apps:
        company_name = a.firma
        if a.company_profile_id:
            cp = db.get(models.CompanyProfile, a.company_profile_id)
            if cp:
                company_name = cp.name_display or company_name
        out.append({
            "id": a.id,
            "firma": a.firma,
            "company_name_display": company_name,
            "rolle": a.rolle,
            "main_status": a.main_status,
            "sub_status": a.sub_status,
            "is_headhunter": a.is_headhunter,
            "zielfirma_bei_hh": a.zielfirma_bei_hh,
            "quelle": a.quelle,
            "datum_bewerbung": a.datum_bewerbung.isoformat() if a.datum_bewerbung else None,
            "letztes_update": a.letztes_update.isoformat() if a.letztes_update else None,
            "ort": a.ort,
            "salary_mismatch": a.salary_mismatch,
            "contacts_count": len(a.contacts),
            "events_count": len(a.events),
        })
    return out


def _company_summary(db: Session, company_id: Optional[int]) -> Optional[dict]:
    if not company_id:
        return None
    cp = db.get(models.CompanyProfile, company_id)
    if not cp:
        return None
    return {
        "id": cp.id,
        "name_display": cp.name_display,
        "industry": cp.industry,
        "company_type": cp.company_type,
        "employee_range": cp.employee_range,
        "hq_city": cp.hq_city,
        "hq_country": cp.hq_country,
        "website": cp.website,
        "description": cp.description,
    }


def _tool_get_application_detail(db: Session, args: dict) -> dict:
    app_id = args.get("application_id")
    a = (
        db.query(models.Application)
        .options(joinedload(models.Application.events), joinedload(models.Application.contacts))
        .filter(models.Application.id == app_id)
        .first()
    )
    if not a:
        return {"error": "not_found", "message": f"No application with id {app_id}."}

    contacts = [
        {
            "id": c.id,
            "name": c.display_name,
            "email": c.email,
            "rolle": c.rolle,
            "linkedin_url": c.linkedin_url,
            "phones": [p.number for p in c.phones],
        }
        for c in a.contacts
    ]

    return {
        "id": a.id,
        "firma": a.firma,
        "rolle": a.rolle,
        "main_status": a.main_status,
        "sub_status": a.sub_status,
        "is_headhunter": a.is_headhunter,
        "zielfirma_bei_hh": a.zielfirma_bei_hh,
        "quelle": a.quelle,
        "wurde_besetzt_von": a.wurde_besetzt_von,
        "ort": a.ort,
        "datum_bewerbung": a.datum_bewerbung.isoformat() if a.datum_bewerbung else None,
        "letztes_update": a.letztes_update.isoformat() if a.letztes_update else None,
        "kommentar": a.kommentar,
        "salary_currency": a.salary_currency,
        "salary_expectation_min": a.salary_expectation_min,
        "salary_expectation_max": a.salary_expectation_max,
        "salary_budget_min": a.salary_budget_min,
        "salary_budget_max": a.salary_budget_max,
        "salary_mismatch": a.salary_mismatch,
        "timeline": _build_timeline_text(a.events),
        "contacts": contacts,
        "company": _company_summary(db, a.company_profile_id),
        "target_company": _company_summary(db, a.target_company_profile_id) if a.is_headhunter else None,
    }


def _tool_get_company_detail(db: Session, args: dict) -> dict:
    company_id = args.get("company_id")
    company_name = args.get("company_name")
    if company_id:
        profile = db.get(models.CompanyProfile, company_id)
        if not profile:
            return {"error": "not_found", "message": f"No company with id {company_id}."}
        return build_company_detail(profile).model_dump()

    if company_name:
        matches = (
            db.query(models.CompanyProfile)
            .filter(models.CompanyProfile.name_display.ilike(f"%{company_name}%"))
            .all()
        )
        if not matches:
            return {"error": "not_found", "message": f"No company matching '{company_name}'."}
        if len(matches) > 1:
            return {
                "error": "ambiguous",
                "message": "Multiple companies match — ask the user which one, or call again with company_id.",
                "matches": [{"id": m.id, "name_display": m.name_display} for m in matches],
            }
        return build_company_detail(matches[0]).model_dump()

    return {"error": "missing_argument", "message": "Provide either company_id or company_name."}


def _tool_get_user_profile(current_user: models.User) -> dict:
    cv_text = current_user.cv_extracted_text
    linkedin_text = current_user.linkedin_profile_text
    result = {
        "vorname": current_user.vorname,
        "nachname": current_user.nachname,
        "cv_text": cv_text,
        "linkedin_text": linkedin_text,
    }
    if not cv_text and not linkedin_text:
        result["note"] = "No CV uploaded and no LinkedIn profile synced yet."
    return result


async def _execute_tool(db: Session, current_user: models.User, name: str, args: dict) -> dict:
    try:
        if name == "list_applications":
            return {"applications": _tool_list_applications(db, args)}
        if name == "get_application_detail":
            return _tool_get_application_detail(db, args)
        if name == "get_company_detail":
            return _tool_get_company_detail(db, args)
        if name == "get_user_profile":
            return _tool_get_user_profile(current_user)
        return {"error": "unknown_tool", "message": f"No such tool: {name}"}
    except Exception as e:
        log.warning("Chat tool {} failed: {}", name, e)
        return {"error": "internal_error", "message": str(e)[:200]}


async def run_chat_turn(db: Session, current_user: models.User, user_text: str) -> tuple[str, list[str]]:
    lang = resolve_ui_language(db, current_user.id)
    system = _SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        language_name=_LANGUAGE_NAMES.get(lang, "English"),
    )

    history_rows = (
        db.query(models.ChatMessage)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(HISTORY_WINDOW_MESSAGES)
        .all()
    )[::-1]

    messages: list[dict] = [{"role": "system", "content": system}]
    messages += [{"role": r.role, "content": r.content} for r in history_rows]
    messages.append({"role": "user", "content": user_text})

    tools_used: list[str] = []
    for _ in range(MAX_TOOL_ITERATIONS):
        msg = await complete_with_tools(db, messages, TOOLS)
        if not msg.tool_calls:
            return msg.content or "", tools_used
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = await _execute_tool(db, current_user, tc.function.name, args)
            tools_used.append(tc.function.name)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    # Iteration cap hit: force a final answer, no more tool access.
    messages.append({
        "role": "user",
        "content": "Please answer now with what you already know, without calling any more tools.",
    })
    msg = await complete_with_tools(db, messages, tools=[])
    return msg.content or "", tools_used
