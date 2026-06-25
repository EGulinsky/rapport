from __future__ import annotations

import io
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter(prefix="/api/export", tags=["export"])

STATUS_LABEL = {
    "prospecting":  "Anbahnung",
    "applied":      "Beworben",
    "hr":           "Gespräch HR",
    "fb":           "Gespräch Fachbereich",
    "waiting":      "Warten auf Entscheidung",
    "negotiating":  "Angebotsverhandlung",
    "signed":       "Vertrag unterschrieben",
    "rejected":     "Absage",
}

TYP_LABEL = {
    "gespräch": "Gespräch",
    "anruf":    "Anruf",
}

# macOS Arial → Linux Liberation Sans (metric-compatible Arial substitute, ships in fonts-liberation)
def _pick_fonts() -> tuple[str, str, str]:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        ),
    ]
    for reg, bold, it in candidates:
        if os.path.exists(reg):
            return reg, bold, it
    raise RuntimeError("No suitable Unicode TTF font found (Arial or Liberation Sans required)")

_FONT_PATH, _FONT_BOLD_PATH, _FONT_IT_PATH = _pick_fonts()

# Landscape A4: 297 × 210 mm, margins 12 mm → usable width = 273 mm
_PAGE_W = 297
_MARGIN  = 12
_USABLE  = _PAGE_W - 2 * _MARGIN  # 273 mm


def _trunc(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"


def _build_pdf(apps: list, appointments: list, since: Optional[date], name: str) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    dated = sorted(
        [a for a in apps if a.datum_bewerbung and (since is None or a.datum_bewerbung >= since)],
        key=lambda a: a.datum_bewerbung,
    )
    today = date.today()
    first = dated[0].datum_bewerbung if dated else today
    last  = dated[-1].datum_bewerbung if dated else today

    class PDF(FPDF):
        def setup(self):
            self.add_font("A",  style="",  fname=_FONT_PATH)
            self.add_font("A",  style="B", fname=_FONT_BOLD_PATH)
            self.add_font("A",  style="I", fname=_FONT_IT_PATH)

        def header(self):
            self.set_font("A", "B", 10)
            self.set_fill_color(30, 64, 120)
            self.set_text_color(255, 255, 255)
            self.rect(0, 0, _PAGE_W, 14, "F")
            self.set_xy(10, 3)
            self.cell(200, 8, "Nachweis der Eigenbemühungen – Bundesagentur für Arbeit")
            self.set_xy(220, 3)
            self.cell(67, 8, f"Stand: {today.strftime('%d.%m.%Y')}", align="R")
            self.set_text_color(0, 0, 0)
            self.ln(14)

        def footer(self):
            self.set_y(-12)
            self.set_font("A", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, f"Seite {self.page_no()} | Erstellt: {today.strftime('%d.%m.%Y')} | {name}", align="C")
            self.set_text_color(0, 0, 0)

    pdf = PDF(orientation="L", unit="mm", format="A4")
    pdf.setup()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(_MARGIN, 18, _MARGIN)
    pdf.add_page()

    # ── Listenüberschrift ─────────────────────────────────────────────────────
    since_label = since.strftime("%d.%m.%Y") if since else "Beginn"
    pdf.set_font("A", "B", 13)
    pdf.set_text_color(30, 64, 120)
    pdf.cell(0, 9, f"Bewerbungsliste ab {since_label} ({len(dated)} Einträge)",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    pdf.set_font("A", "I", 8)
    pdf.set_text_color(100, 100, 100)
    period = f"{first.strftime('%d.%m.%Y')} bis {last.strftime('%d.%m.%Y')}"
    pdf.cell(0, 4, f"Zeitraum: {period}  |  Name: {name}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # ── Bewerbungs-Tabelle ────────────────────────────────────────────────────
    # Cols: # | Datum | Unternehmen | Position | Status | Quelle
    # Total must equal _USABLE = 273 mm
    cw = [8, 26, 82, 92, 43, 22]
    ch = ["#", "Datum", "Unternehmen", "Position", "Status", "Quelle"]

    def table_header():
        pdf.set_fill_color(30, 64, 120)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("A", "B", 8)
        for h, w in zip(ch, cw):
            pdf.cell(w, 7, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_text_color(0, 0, 0)

    table_header()
    fill = False

    for i, a in enumerate(dated, 1):
        datum = a.datum_bewerbung.strftime("%d.%m.%Y") if a.datum_bewerbung else "—"

        if a.is_headhunter and a.zielfirma_bei_hh:
            firma_raw = f"{a.zielfirma_bei_hh} ({a.firma})"
        else:
            firma_raw = a.firma or ""
        firma  = _trunc(firma_raw, 46)
        rolle  = _trunc(a.rolle or "", 52)
        status = STATUS_LABEL.get(a.main_status, a.main_status)
        quelle = _trunc(a.quelle or "—", 14)

        bg = (245, 248, 255) if fill else (255, 255, 255)
        pdf.set_fill_color(*bg)
        pdf.set_font("A", "", 7)
        row_h = 5
        pdf.cell(cw[0], row_h, str(i),   border="LRB", fill=True, align="C")
        pdf.cell(cw[1], row_h, datum,     border="LRB", fill=True)
        pdf.cell(cw[2], row_h, firma,     border="LRB", fill=True)
        pdf.cell(cw[3], row_h, rolle,     border="LRB", fill=True)
        pdf.cell(cw[4], row_h, status,    border="LRB", fill=True)
        pdf.cell(cw[5], row_h, quelle,    border="LRB", fill=True)
        pdf.ln()
        fill = not fill

        if i % 58 == 0 and i < len(dated):
            pdf.add_page()
            table_header()
            fill = False

    # ── Terminübersicht (letzte 4 Wochen) ────────────────────────────────────
    if appointments:
        pdf.ln(6)
        pdf.set_font("A", "B", 13)
        pdf.set_text_color(30, 64, 120)
        four_weeks_ago = (today - timedelta(weeks=4)).strftime("%d.%m.%Y")
        pdf.cell(0, 9, f"Termine der letzten 4 Wochen ({four_weeks_ago} – {today.strftime('%d.%m.%Y')})",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # Cols: Datum | Art | Unternehmen | Position | Thema/Titel
        # Total = 273 mm
        aw = [26, 24, 72, 82, 69]
        ah = ["Datum", "Art", "Unternehmen", "Position", "Thema / Titel"]

        def appt_header():
            pdf.set_fill_color(30, 64, 120)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("A", "B", 8)
            for h, w in zip(ah, aw):
                pdf.cell(w, 7, h, border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_text_color(0, 0, 0)

        appt_header()
        fill2 = False

        for appt in appointments:
            datum  = appt.datum.strftime("%d.%m.%Y") if appt.datum else "—"
            art    = TYP_LABEL.get(appt.typ or "", appt.typ or "—")
            firma  = _trunc(appt.application.firma or "", 40) if appt.application else "—"
            rolle  = _trunc(appt.application.rolle or "", 46) if appt.application else "—"
            titel  = _trunc(appt.titel or "", 40)

            bg = (245, 248, 255) if fill2 else (255, 255, 255)
            pdf.set_fill_color(*bg)
            pdf.set_font("A", "", 7)
            row_h = 5
            pdf.cell(aw[0], row_h, datum,  border="LRB", fill=True)
            pdf.cell(aw[1], row_h, art,    border="LRB", fill=True)
            pdf.cell(aw[2], row_h, firma,  border="LRB", fill=True)
            pdf.cell(aw[3], row_h, rolle,  border="LRB", fill=True)
            pdf.cell(aw[4], row_h, titel,  border="LRB", fill=True)
            pdf.ln()
            fill2 = not fill2

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


@router.get("/pdf")
def export_pdf(
    since: Optional[date] = Query(None, description="Nur Bewerbungen ab diesem Datum (YYYY-MM-DD)"),
    name: str = Query("Eugen Gulinsky", description="Name für Kopf- und Fußzeile"),
    db: Session = Depends(get_db),
):
    apps = db.query(models.Application).all()

    cutoff = date.today() - timedelta(weeks=4)
    appointments = (
        db.query(models.Event)
        .join(models.Application, models.Event.application_id == models.Application.id)
        .filter(
            models.Event.typ.in_(["gespräch", "anruf"]),
            models.Event.datum >= cutoff,
        )
        .order_by(models.Event.datum)
        .all()
    )

    pdf_bytes = _build_pdf(apps, appointments, since, name)

    today = date.today().strftime("%Y-%m-%d")
    since_str = since.strftime("%Y-%m-%d") + "_" if since else ""
    filename = f"Eigenbemühungen_{since_str}{today}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
