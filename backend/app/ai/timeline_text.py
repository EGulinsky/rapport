"""Shared chronological timeline formatter, fed into LLM prompts that need an
application's activity history as context (rapportGPT's get_application_detail
tool in ai/chat.py, and the match-score/success-probability prompts in
ai/tasks.py). Kept as its own module rather than living in ai/chat.py so
ai/tasks.py doesn't need to import that module's router-layer dependencies
(ai/chat.py imports app.routers.companies) just to reuse this one function."""
from __future__ import annotations

from datetime import date


def build_timeline_text(events: list) -> str:
    """Chronological, full-content timeline format — well-tested, readable
    shape for feeding an LLM an application's history."""
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
