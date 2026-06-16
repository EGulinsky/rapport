from __future__ import annotations

import io
import os
from datetime import date
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


def _build_pdf(apps: list, since: Optional[date], name: str) -> bytes:
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
            self.rect(0, 0, 210, 14, "F")
            self.set_xy(10, 3)
            self.cell(140, 8, "Nachweis der Eigenbemühungen – Bundesagentur für Arbeit")
            self.set_xy(150, 3)
            self.cell(50, 8, f"Stand: {today.strftime('%d.%m.%Y')}", align="R")
            self.set_text_color(0, 0, 0)
            self.ln(14)

        def footer(self):
            self.set_y(-12)
            self.set_font("A", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, f"Seite {self.page_no()} | Erstellt: {today.strftime('%d.%m.%Y')} | {name}", align="C")
            self.set_text_color(0, 0, 0)

    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.setup()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 18, 12)
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

    # ── Tabellen-Header ───────────────────────────────────────────────────────
    cw = [8, 22, 62, 62, 24, 12]
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
            firma = f"{a.zielfirma_bei_hh[:28]} ({a.firma[:16]})"
        else:
            firma = (a.firma or "")[:38]

        rolle  = (a.rolle or "")[:40]
        status = STATUS_LABEL.get(a.main_status, a.main_status)
        quelle = (a.quelle or "—")[:10]

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

        if i % 48 == 0 and i < len(dated):
            pdf.add_page()
            table_header()
            fill = False

    # ── Unterschriftsfeld ─────────────────────────────────────────────────────
    pdf.ln(14)
    pdf.set_font("A", "", 9)
    pdf.cell(0, 5, "Ich versichere die Richtigkeit und Vollständigkeit der oben gemachten Angaben.",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(14)
    pdf.cell(75, 5, "_" * 38, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(15, 5, "",        new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(75, 5, "_" * 38, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("A", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(75, 4, "Ort, Datum",              new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(15, 4, "",                         new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(75, 4, f"Unterschrift ({name})",   new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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
    pdf_bytes = _build_pdf(apps, since, name)

    today = date.today().strftime("%Y-%m-%d")
    since_str = since.strftime("%Y-%m-%d") + "_" if since else ""
    filename = f"Eigenbemühungen_{since_str}{today}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
