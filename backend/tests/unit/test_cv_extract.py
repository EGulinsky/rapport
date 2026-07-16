"""L0 Unit — app/cv_extract.py: CV text extraction for the AI assessment
prompt. Round-trips real PDF/DOCX files (written with fpdf2/python-docx, both
already dependencies) rather than mocking pdfplumber/docx internals — a
genuine extraction test catches library-integration breakage a mock can't."""
import pytest

from app.cv_extract import MAX_TEXT_CHARS, extract_cv_text

pytestmark = pytest.mark.unit


def _write_pdf(path, text: str) -> None:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    pdf.output(str(path))


def _write_docx(path, paragraphs: list[str]) -> None:
    import docx
    doc = docx.Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(str(path))


class TestExtractCvText:
    def test_positiv_pdf_wird_extrahiert(self, tmp_path):
        pdf_path = tmp_path / "cv.pdf"
        _write_pdf(pdf_path, "Jane Doe - Senior Software Engineer")

        result = extract_cv_text(str(pdf_path))

        assert result is not None
        assert "Jane Doe" in result
        assert "Senior Software Engineer" in result

    def test_positiv_docx_wird_extrahiert(self, tmp_path):
        docx_path = tmp_path / "cv.docx"
        _write_docx(docx_path, ["Jane Doe", "Senior Software Engineer", "10 years experience"])

        result = extract_cv_text(str(docx_path))

        assert result == "Jane Doe Senior Software Engineer 10 years experience"

    def test_negativ_fehlende_datei_liefert_none(self, tmp_path):
        result = extract_cv_text(str(tmp_path / "nonexistent.pdf"))
        assert result is None

    def test_negativ_doc_liefert_none(self, tmp_path):
        """Legacy binary .doc has no extraction library anywhere in this repo
        (agent included) — must degrade to None, not raise."""
        doc_path = tmp_path / "cv.doc"
        doc_path.write_bytes(b"not a real .doc file")

        result = extract_cv_text(str(doc_path))

        assert result is None

    def test_negativ_leeres_pdf_liefert_none(self, tmp_path):
        pdf_path = tmp_path / "empty.pdf"
        _write_pdf(pdf_path, "")

        result = extract_cv_text(str(pdf_path))

        assert result is None

    def test_negativ_korrupte_pdf_liefert_none_statt_exception(self, tmp_path):
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 not actually valid pdf content")

        result = extract_cv_text(str(pdf_path))

        assert result is None

    def test_positiv_kappt_bei_max_zeichen(self, tmp_path):
        docx_path = tmp_path / "long.docx"
        _write_docx(docx_path, ["word " * (MAX_TEXT_CHARS // 4)])

        result = extract_cv_text(str(docx_path))

        assert result is not None
        assert len(result) == MAX_TEXT_CHARS

    def test_negativ_ueberschreitet_timeout_liefert_none_statt_zu_haengen(self, tmp_path):
        """Regression test for the 2026-07-16 production incident: pdfplumber
        pathologically spun at ~100% CPU for minutes on a real CV, blocking
        app startup indefinitely since the migration backfill called this
        synchronously. A timeout far shorter than even a fast subprocess
        spawn+import can complete in (real extraction of this trivial file
        normally finishes well under 1s, see test_positiv_pdf_wird_extrahiert)
        proves the call returns promptly instead of waiting on the child."""
        import time

        pdf_path = tmp_path / "cv.pdf"
        _write_pdf(pdf_path, "Jane Doe - Senior Software Engineer")

        t0 = time.monotonic()
        result = extract_cv_text(str(pdf_path), timeout=0.01)
        elapsed = time.monotonic() - t0

        assert result is None
        assert elapsed < 5
