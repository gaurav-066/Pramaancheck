import base64
from typing import Dict, Any, Optional
from fpdf import FPDF


# ---------------------------------------------------------------------------
# Unicode Sanitiser — Helvetica is Latin-1 only; strip/replace anything else
# ---------------------------------------------------------------------------

_REPLACEMENTS = [
    ("\u20b9", "Rs."),   # ₹
    ("\u2013", "-"),     # –
    ("\u2014", "-"),     # —
    ("\u201c", '"'),     # "
    ("\u201d", '"'),     # "
    ("\u2018", "'"),     # '
    ("\u2019", "'"),     # '
    ("\u2026", "..."),   # …
    ("\u2022", "*"),     # •
    ("\u00d7", "x"),     # ×
    ("\u00ae", "(R)"),   # ®
    ("\u00a9", "(C)"),   # ©
]


def _safe(value, max_len: Optional[int] = None) -> str:
    """Return a Latin-1-safe string suitable for Helvetica in fpdf2."""
    text = str(value) if value is not None else ""
    for old, new in _REPLACEMENTS:
        text = text.replace(old, new)
    # Drop any remaining non-Latin-1 characters
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    if max_len is not None:
        text = text[:max_len]
    return text


# ---------------------------------------------------------------------------
# PDF Generator — fpdf2 2.8.x compatible (no deprecated ln= parameter)
# ---------------------------------------------------------------------------

def generate_pdf_report(scan_data: Dict[str, Any], output_path: Optional[str] = None) -> bytes:
    """
    Generates a formal Legal Metrology Compliance Inspection PDF report.

    Returns PDF content as bytes.
    If output_path is given, also writes the bytes to that path (best-effort).
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Title Header ──────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(6, 95, 212)
    pdf.cell(
        0, 10,
        "PramaanCheck - Legal Metrology Compliance Report",
        new_x="LMARGIN", new_y="NEXT", align="L"
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        0, 6,
        "Under Legal Metrology (Packaged Commodities) Rules, 2011",
        new_x="LMARGIN", new_y="NEXT", align="L"
    )
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # ── Metadata Block ────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, f"Scan ID: #{scan_data.get('id', 'N/A')}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 6, _safe(f"Image File: {scan_data.get('image_name', 'Unknown')}"))
    pdf.cell(
        95, 6,
        f"Inspector Role: {_safe(scan_data.get('user_role', 'inspector')).capitalize()}",
        new_x="LMARGIN", new_y="NEXT"
    )
    pdf.cell(95, 6, _safe(f"Scan Timestamp: {scan_data.get('created_at', 'N/A')}"))
    pdf.cell(
        95, 6,
        f"Overall Status: {_safe(scan_data.get('overall_status', 'UNKNOWN'))}",
        new_x="LMARGIN", new_y="NEXT"
    )
    pdf.cell(
        95, 6,
        f"Compliance Score: {scan_data.get('compliance_score', 0)}%",
        new_x="LMARGIN", new_y="NEXT"
    )
    note = scan_data.get('note')
    if note:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(35, 6, "Investigation Note: ")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _safe(note), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # ── Rule 7 Font Height Section ────────────────────────────────────────
    font_check = scan_data.get("font_check") or {}
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "1. Rule 7 Font Height & Width Verification", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0, 6,
        _safe(font_check.get("rule_7_details", "No font height details recorded."))
    )
    pdf.ln(4)

    # ── Rule 6 Checklist Table ────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "2. Rule 6 Mandatory Declarations Checklist", new_x="LMARGIN", new_y="NEXT")

    # Table header row
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(60, 7, "Declaration Rule", border=1, fill=True)
    pdf.cell(25, 7, "Section",           border=1, fill=True)
    pdf.cell(25, 7, "Status",            border=1, fill=True)
    pdf.cell(80, 7, "Inspection Details", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    # Table data rows
    pdf.set_font("Helvetica", "", 8)
    rule_results = scan_data.get("rule_results") or {}
    rules = rule_results.get("rules") or []

    for r in rules:
        status_str = r.get("status", "FAIL")
        rule_name  = _safe(r.get("rule_name",   ""), 32)
        act_sec    = _safe(r.get("act_section",  "Rule 6"), 14)
        details    = _safe(r.get("details",      ""), 55)

        pdf.cell(60, 6, rule_name,  border=1)
        pdf.cell(25, 6, act_sec,    border=1)
        pdf.cell(25, 6, status_str, border=1)
        pdf.cell(80, 6, details,    border=1, new_x="LMARGIN", new_y="NEXT")

    # ── Footer ────────────────────────────────────────────────────────────
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0, 4,
        _safe(
            "Note: This report is automatically generated by PramaanCheck. "
            "Surface area positioning rules for Principle Display Panel (PDP) "
            "are reserved for v2."
        )
    )

    # ── Output ────────────────────────────────────────────────────────────
    pdf_bytes = bytes(pdf.output())

    if output_path:
        try:
            with open(output_path, "wb") as fh:
                fh.write(pdf_bytes)
        except Exception as exc:
            print(f"[Report Gen] Could not write to {output_path}: {exc}")

    return pdf_bytes


def generate_pdf_base64(scan_data: Dict[str, Any]) -> str:
    """Convenience wrapper that returns PDF as a base64 string."""
    return base64.b64encode(generate_pdf_report(scan_data)).decode("ascii")
