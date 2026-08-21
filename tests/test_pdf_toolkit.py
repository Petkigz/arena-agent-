"""PdfToolkit tests — merge/split/extract/metadata/text/form, deterministic
(real pypdf, no LLM) against tiny generated PDFs."""

from pypdf import PdfWriter

from app.tools.pdf_toolkit import PdfToolkit


def _make_pdf(path, pages=1):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)


def test_merge_two_pdfs(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, 1)
    _make_pdf(b, 2)
    out = tmp_path / "merged.pdf"

    res = PdfToolkit.merge_pdfs([str(a), str(b)], str(out))
    assert res["success"] is True
    meta = PdfToolkit.get_metadata(str(out))
    assert meta["page_count"] == 3


def test_merge_requires_two_inputs(tmp_path):
    a = tmp_path / "a.pdf"
    _make_pdf(a)
    assert PdfToolkit.merge_pdfs([str(a)])["success"] is False
    assert PdfToolkit.merge_pdfs([])["success"] is False


def test_merge_missing_file(tmp_path):
    a = tmp_path / "a.pdf"
    _make_pdf(a)
    res = PdfToolkit.merge_pdfs([str(a), str(tmp_path / "nope.pdf")])
    assert res["success"] is False
    assert "not found" in res["error"].lower()


def test_split_three_pages(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 3)
    res = PdfToolkit.split_pdf(str(p), str(tmp_path / "out"))
    assert res["success"] is True
    assert res["count"] == 3
    assert len(res["parts"]) == 3


def test_split_two_per_chunk(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 5)
    res = PdfToolkit.split_pdf(str(p), str(tmp_path / "out"), pages_per_split=2)
    assert res["success"] is True
    assert res["count"] == 3  # 2 + 2 + 1


def test_extract_pages(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 3)
    out = tmp_path / "ex.pdf"
    res = PdfToolkit.extract_pages(str(p), [1, 3], str(out))
    assert res["success"] is True
    assert PdfToolkit.get_metadata(str(out))["page_count"] == 2


def test_extract_out_of_range(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 2)
    res = PdfToolkit.extract_pages(str(p), [5])
    assert res["success"] is False
    assert "out of range" in res["error"]


def test_metadata_page_count(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 4)
    res = PdfToolkit.get_metadata(str(p))
    assert res["success"] is True
    assert res["page_count"] == 4


def test_metadata_rejects_non_pdf(tmp_path):
    t = tmp_path / "x.txt"
    t.write_text("hello")
    assert PdfToolkit.get_metadata(str(t))["success"] is False


def test_extract_text_blank_pdf(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 1)
    res = PdfToolkit.extract_text(str(p))
    assert res["success"] is True
    assert res["page_count"] == 1


def test_fill_form_no_fields(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, 1)
    res = PdfToolkit.fill_form(str(p), {"name": "x"})
    assert res["success"] is False
    assert "no fillable form fields" in res["error"].lower()


def test_missing_file_everywhere(tmp_path):
    nope = tmp_path / "nope.pdf"
    assert PdfToolkit.get_metadata(str(nope))["success"] is False
    assert PdfToolkit.extract_text(str(nope))["success"] is False
    assert PdfToolkit.split_pdf(str(nope))["success"] is False
    assert PdfToolkit.extract_pages(str(nope), [1])["success"] is False
