"""InvoiceGenerator tests — deterministic PDF generation and totals math."""

from pathlib import Path

from app.tools.invoice_generator import InvoiceGenerator
from app.tools.pdf_toolkit import PdfToolkit


def _items():
    return [
        {"description": "Consulting", "quantity": 2, "unit_price": 100.0},
        {"description": "Hosting", "quantity": 1, "unit_price": 25.50},
    ]


def test_generate_invoice_totals(tmp_path):
    out = tmp_path / "inv.pdf"
    res = InvoiceGenerator.generate_invoice(
        to_name="Acme Corp",
        line_items=_items(),
        currency="$",
        tax_rate=10,
        output_path=str(out),
    )
    assert res["success"] is True
    assert res["subtotal"] == 225.50
    assert res["tax"] == 22.55
    assert res["total"] == 248.05
    assert res["line_items_count"] == 2
    assert out.exists()


def test_invoice_is_a_one_page_pdf(tmp_path):
    out = tmp_path / "inv.pdf"
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=_items(), output_path=str(out))
    assert res["success"] is True
    meta = PdfToolkit.get_metadata(str(out))
    assert meta["success"] is True
    assert meta["page_count"] == 1


def test_requires_to_name(tmp_path):
    res = InvoiceGenerator.generate_invoice(to_name="", line_items=_items(), output_path=str(tmp_path / "x.pdf"))
    assert res["success"] is False
    assert "to_name" in res["error"]


def test_requires_line_items(tmp_path):
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=[], output_path=str(tmp_path / "x.pdf"))
    assert res["success"] is False


def test_rejects_malformed_line_items(tmp_path):
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=[{"description": "x"}], output_path=str(tmp_path / "x.pdf"))
    assert res["success"] is False  # missing unit_price

    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items="notalist", output_path=str(tmp_path / "x.pdf"))
    assert res["success"] is False


def test_rejects_negative_values(tmp_path):
    res = InvoiceGenerator.generate_invoice(
        to_name="Acme",
        line_items=[{"description": "x", "quantity": -1, "unit_price": 5}],
        output_path=str(tmp_path / "x.pdf"),
    )
    assert res["success"] is False


def test_rejects_negative_tax(tmp_path):
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=_items(), tax_rate=-5)
    assert res["success"] is False


def test_quote_and_receipt_types(tmp_path):
    for dt in ("quote", "receipt"):
        out = tmp_path / f"{dt}.pdf"
        res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=_items(), document_type=dt, output_path=str(out))
        assert res["success"] is True
        assert res["document_type"] == dt
        assert out.exists()


def test_rejects_unknown_document_type(tmp_path):
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=_items(), document_type="memo")
    assert res["success"] is False


def test_default_output_path_inside_workspace():
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=_items())
    assert res["success"] is True
    assert Path(res["output_path"]).exists()


def test_defaults_number_and_date(tmp_path):
    out = tmp_path / "inv.pdf"
    res = InvoiceGenerator.generate_invoice(to_name="Acme", line_items=_items(), output_path=str(out))
    assert res["success"] is True
    assert res["invoice_number"]
    assert res["tax_rate"] == 0.0
    assert res["tax"] == 0.0
    assert res["total"] == res["subtotal"]
