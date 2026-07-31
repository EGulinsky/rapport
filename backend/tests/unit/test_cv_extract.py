"""L0 Unit — app/cv_extract.py: CV text extraction for the AI assessment
prompt. Round-trips real PDF/DOCX files (written with fpdf2/python-docx, both
already dependencies) rather than mocking pdfplumber/docx internals — a
genuine extraction test catches library-integration breakage a mock can't."""
import pytest

from app.cv_extract import MAX_TEXT_CHARS, extract_cv_text, extract_text_from_file

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


class TestExtractTextFromFile:
    """L0 Unit — the generalized extract_text_from_file(), used for both the
    CV (via extract_cv_text()'s thin wrapper) and per-application
    job-description attachments (ai/jd_resolve.py)."""

    def test_positiv_txt_wird_extrahiert(self, tmp_path):
        txt_path = tmp_path / "jd.txt"
        txt_path.write_text("Senior Backend Engineer — Python, Kubernetes, 5+ years", encoding="utf-8")

        result = extract_text_from_file(str(txt_path))

        assert result == "Senior Backend Engineer — Python, Kubernetes, 5+ years"

    def test_positiv_md_wird_extrahiert(self, tmp_path):
        md_path = tmp_path / "jd.md"
        md_path.write_text("# Senior Backend Engineer\n\nRequirements: Python, Kubernetes", encoding="utf-8")

        result = extract_text_from_file(str(md_path))

        assert result == "# Senior Backend Engineer\n\nRequirements: Python, Kubernetes"

    def test_positiv_pdf_wird_extrahiert(self, tmp_path):
        pdf_path = tmp_path / "jd.pdf"
        _write_pdf(pdf_path, "Senior Backend Engineer")

        result = extract_text_from_file(str(pdf_path))

        assert result is not None
        assert "Senior Backend Engineer" in result

    def test_positiv_eigener_max_chars_wird_respektiert(self, tmp_path):
        txt_path = tmp_path / "jd.txt"
        txt_path.write_text("word " * 2000, encoding="utf-8")

        result = extract_text_from_file(str(txt_path), max_chars=100)

        assert result is not None
        assert len(result) == 100

    def test_negativ_nicht_unterstuetzte_endung_liefert_none(self, tmp_path):
        path = tmp_path / "jd.xyz"
        path.write_text("irrelevant", encoding="utf-8")

        result = extract_text_from_file(str(path))

        assert result is None

    def test_regression_extract_cv_text_verhaelt_sich_unveraendert(self, tmp_path):
        """extract_cv_text() must still use MAX_TEXT_CHARS, not
        extract_text_from_file()'s own default — guards the thin-wrapper
        refactor against silently changing the CV's cap."""
        docx_path = tmp_path / "long.docx"
        _write_docx(docx_path, ["word " * (MAX_TEXT_CHARS // 4)])

        result = extract_cv_text(str(docx_path))

        assert result is not None
        assert len(result) == MAX_TEXT_CHARS
