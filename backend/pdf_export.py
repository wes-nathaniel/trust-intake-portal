"""PDF generation for completed trust intake cases."""
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

NAVY = HexColor("#1C252E")
BRONZE = HexColor("#C5A880")
SAND = HexColor("#F6F4F0")
SAND_DARK = HexColor("#EBE7DF")
MUTED = HexColor("#64748B")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("T", parent=ss["Title"], fontName="Times-Bold",
                                fontSize=28, textColor=NAVY, leading=32, alignment=TA_LEFT),
        "h2": ParagraphStyle("H2", parent=ss["Heading2"], fontName="Times-Bold",
                             fontSize=16, textColor=NAVY, leading=20, spaceBefore=16, spaceAfter=8),
        "h3": ParagraphStyle("H3", parent=ss["Heading3"], fontName="Times-Bold",
                             fontSize=12, textColor=BRONZE, leading=15, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("B", parent=ss["BodyText"], fontName="Helvetica",
                               fontSize=10, textColor=black, leading=14),
        "muted": ParagraphStyle("M", parent=ss["BodyText"], fontName="Helvetica",
                                fontSize=9, textColor=MUTED, leading=12),
        "label": ParagraphStyle("L", parent=ss["BodyText"], fontName="Helvetica-Bold",
                                fontSize=9, textColor=MUTED, leading=12),
    }


def _mask_ssn(ssn: str) -> str:
    digits = "".join(c for c in (ssn or "") if c.isdigit())
    if len(digits) < 4:
        return "—"
    return f"XXX-XX-{digits[-4:]}"


def _kv_table(rows, styles):
    """rows = [(label, value)]"""
    data = []
    for k, v in rows:
        data.append([
            Paragraph(k.upper(), styles["label"]),
            Paragraph(str(v) if v not in (None, "") else "—", styles["body"]),
        ])
    t = Table(data, colWidths=[1.6 * inch, 4.8 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, SAND_DARK),
    ]))
    return t


def _fmt_addr(a):
    if not a:
        return ""
    parts = [a.get("line1", ""), a.get("line2", ""),
             f"{a.get('city','')} {a.get('state','')} {a.get('zip','')}".strip(),
             a.get("country", "")]
    return ", ".join([p for p in parts if p])


def _header_footer(branding):
    business = (branding or {}).get("business_name", "IGC Trust Portal")

    def on_page(canvas, doc):
        canvas.saveState()
        # Header bar
        canvas.setFillColor(NAVY)
        canvas.rect(0, letter[1] - 0.6 * inch, letter[0], 0.6 * inch, fill=1, stroke=0)
        canvas.setFillColor(SAND)
        canvas.setFont("Times-Bold", 14)
        canvas.drawString(0.6 * inch, letter[1] - 0.4 * inch, business)
        canvas.setFillColor(BRONZE)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(letter[0] - 0.6 * inch, letter[1] - 0.4 * inch, "TRUST INTAKE SUMMARY")
        # Footer - multi-line branding + disclaimer
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(0.6 * inch, 0.58 * inch,
                          "Prepared by Iron Gate Consulting  \u00B7  Reviewed through military legal benefits")
        canvas.setFont("Helvetica", 7)
        canvas.drawString(0.6 * inch, 0.45 * inch,
                          "Not legal advice. Trust laws vary by state; seek independent counsel as needed.")
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.6 * inch, 0.3 * inch,
                          f"Generated {datetime.now().strftime('%B %d, %Y %H:%M UTC')}")
        canvas.drawRightString(letter[0] - 0.6 * inch, 0.3 * inch,
                               f"Page {doc.page}")
        canvas.restoreState()
    return on_page


def build_intake_pdf(case: dict, branding: dict) -> bytes:
    s = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.7 * inch,
                            title=f"Trust Intake {case.get('id','')[:8]}")
    flow = []

    # Cover
    flow.append(Paragraph("Trust Intake Summary", s["title"]))
    flow.append(Spacer(1, 6))
    trust_name_display = case.get("trust_name") or "(Trust name pending)"
    flow.append(Paragraph(
        f"<b>{trust_name_display}</b>",
        s["body"]))
    flow.append(Paragraph(
        f"Case #{case.get('id','')[:8].upper()} — "
        f"{'Joint Trust' if case.get('trust_type') == 'joint' else 'Single Trust'}",
        s["muted"]))
    flow.append(Spacer(1, 14))

    client_rows = [
        ("Trust name", case.get("trust_name") or "—"),
        ("Client", case.get("client_name") or case.get("client_email", "")),
        ("Email", case.get("client_email", "")),
        ("Status", case.get("status", "")),
        ("Created", case.get("created_at", "")[:10]),
        ("Last Updated", case.get("updated_at", "")[:10]),
    ]
    flow.append(_kv_table(client_rows, s))
    flow.append(Spacer(1, 12))

    # Grantors
    flow.append(Paragraph(f"Grantors ({len(case.get('grantors', []))})", s["h2"]))
    for i, g in enumerate(case.get("grantors", []), 1):
        flow.append(Paragraph(f"Grantor {i}", s["h3"]))
        flow.append(_kv_table([
            ("Full legal name", g.get("full_legal_name")),
            ("Middle name", g.get("middle_name") or ""),
            ("Date of birth", g.get("date_of_birth")),
            ("SSN", _mask_ssn(g.get("ssn"))),
            ("Phone", g.get("phone")),
            ("Secondary phone", g.get("secondary_phone") or ""),
            ("Email", g.get("email")),
            ("Marital status", g.get("marital_status")),
            ("Citizenship", g.get("citizenship")),
            ("Residential address", _fmt_addr(g.get("address"))),
            ("Notes", g.get("notes") or ""),
        ], s))
        flow.append(Spacer(1, 10))

    # Trustee
    flow.append(Paragraph("Trustee", s["h2"]))
    trustee = (case.get("trustees") or [None])[0]
    if trustee:
        flow.append(_kv_table([
            ("Full legal name", trustee.get("full_legal_name")),
            ("Relationship", trustee.get("relationship")),
            ("Phone", trustee.get("phone")),
            ("Email", trustee.get("email")),
            ("Address", _fmt_addr(trustee.get("address"))),
            ("Notes", trustee.get("notes") or ""),
        ], s))
    else:
        flow.append(Paragraph("Not provided.", s["muted"]))
    flow.append(Spacer(1, 10))

    # Successor trustees
    sct = case.get("successor_trustees", [])
    flow.append(Paragraph(f"Successor Trustees ({len(sct)})", s["h2"]))
    for i, t in enumerate(sct, 1):
        flow.append(Paragraph(f"Successor {i}", s["h3"]))
        flow.append(_kv_table([
            ("Full legal name", t.get("full_legal_name")),
            ("Relationship", t.get("relationship")),
            ("Phone", t.get("phone")),
            ("Email", t.get("email")),
            ("Address", _fmt_addr(t.get("address"))),
        ], s))
        flow.append(Spacer(1, 8))

    # Beneficiaries
    bens = case.get("beneficiaries", [])
    flow.append(PageBreak())
    flow.append(Paragraph(f"Beneficiaries ({len(bens)})", s["h2"]))
    for i, b in enumerate(bens, 1):
        flow.append(Paragraph(f"Beneficiary {i}", s["h3"]))
        rows = [
            ("Full legal name", b.get("full_legal_name")),
            ("Date of birth", b.get("date_of_birth")),
            ("Relationship", b.get("relationship")),
            ("Share", f"{b.get('percentage', 0)}%"),
            ("Phone", b.get("phone") or ""),
            ("Email", b.get("email") or ""),
            ("Address", _fmt_addr(b.get("address"))),
            ("Special instructions", b.get("special_instructions") or ""),
        ]
        if b.get("contingent_name"):
            rows += [
                ("Contingent name", b.get("contingent_name")),
                ("Contingent relationship", b.get("contingent_relationship") or ""),
                ("Contingent phone", b.get("contingent_phone") or ""),
            ]
        flow.append(_kv_table(rows, s))
        flow.append(Spacer(1, 8))

    total_pct = sum(b.get("percentage", 0) or 0 for b in bens)
    flow.append(Paragraph(f"Total allocated: <b>{total_pct}%</b>", s["muted"]))
    flow.append(Spacer(1, 10))

    # Assets
    assets = case.get("assets", [])
    type_label = {
        "bank": "Bank Account", "real_estate": "Real Estate", "vehicle": "Vehicle",
        "life_insurance": "Life Insurance", "investment": "Investment",
        "business": "Business Interest", "digital": "Digital Asset",
    }
    flow.append(Paragraph(f"Assets ({len(assets)})", s["h2"]))
    for i, a in enumerate(assets, 1):
        flow.append(Paragraph(f"{i}. {type_label.get(a.get('asset_type'), a.get('asset_type', ''))}", s["h3"]))
        rows = [
            ("Institution / Property",
             a.get("institution_name") or a.get("property_address") or ""),
            ("Account / policy #", a.get("account_number") or ""),
            ("Institution address", a.get("institution_address") or ""),
            ("Estimated value",
             f"${float(a.get('estimated_value')):,.2f}" if a.get("estimated_value") else ""),
            ("Notes", a.get("notes") or ""),
        ]
        flow.append(_kv_table(rows, s))
        flow.append(Spacer(1, 6))

    total_value = sum(float(a.get("estimated_value") or 0) for a in assets)
    if total_value > 0:
        flow.append(Paragraph(f"Total estimated value: <b>${total_value:,.2f}</b>", s["muted"]))
    flow.append(Spacer(1, 10))

    # EIN
    flow.append(Paragraph("EIN Workflow", s["h2"]))
    ein = case.get("ein") or {}
    flow.append(_kv_table([
        ("SSN", _mask_ssn(ein.get("ssn")) if ein.get("ssn") else "—"),
        ("Authorized", "Yes" if ein.get("authorized") else "No"),
        ("EIN Requested", "Yes" if case.get("ein_requested") else "No"),
        ("EIN Letter on file", case.get("ein_letter", {}).get("filename", "—") if case.get("ein_letter") else "—"),
    ], s))

    # Documents
    docs = [d for d in (case.get("documents") or []) if not d.get("is_deleted")]
    flow.append(Paragraph(f"Documents ({len(docs)})", s["h2"]))
    if docs:
        data = [[Paragraph("<b>Type</b>", s["label"]),
                 Paragraph("<b>Filename</b>", s["label"]),
                 Paragraph("<b>Uploaded</b>", s["label"])]]
        for d in docs:
            data.append([
                Paragraph(d.get("doc_type", "").replace("_", " ").title(), s["body"]),
                Paragraph(d.get("filename", ""), s["body"]),
                Paragraph(d.get("uploaded_at", "")[:10], s["body"]),
            ])
        t = Table(data, colWidths=[2.0 * inch, 3.0 * inch, 1.4 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SAND_DARK),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, SAND_DARK),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(t)
    else:
        flow.append(Paragraph("No documents uploaded.", s["muted"]))

    flow.append(Spacer(1, 18))
    flow.append(Paragraph(
        "This document is a summary of information provided during the trust intake and is "
        "intended solely for preparation of estate planning documents. SSNs have been masked "
        "for security.",
        s["muted"]))

    # --- Legal Disclosures page ---
    flow.append(PageBreak())
    flow.append(Paragraph("Legal Disclosures & Notices", s["h2"]))
    flow.append(Spacer(1, 6))
    flow.append(Paragraph(
        "<b>Not legal advice.</b> This trust has been reviewed for accuracy and completeness through my military "
        "legal benefits. All documents are prepared using standardized trust templates that are commonly "
        "reviewed by military legal professionals. I am not an attorney and do not provide legal advice. "
        "Clients may seek independent legal counsel at any time.",
        s["body"]))
    flow.append(Spacer(1, 10))
    flow.append(Paragraph(
        "<b>State-specific advisory.</b> Trust laws vary by state. Clients are responsible for ensuring the trust "
        "meets their personal legal needs and may seek independent legal counsel in their state at any time.",
        s["body"]))
    flow.append(Spacer(1, 10))
    flow.append(Paragraph(
        "<b>Notarization required.</b> Your trust must be printed and notarized to become legally valid. "
        "Please sign in the presence of a notary public and retain the original notarized copy with your "
        "important records.",
        s["body"]))

    # Business / SOS advisory if any business asset is present
    assets_now = case.get("assets") or []
    has_business_asset = any(a.get("asset_type") == "business" for a in assets_now)
    if has_business_asset:
        flow.append(Spacer(1, 10))
        flow.append(Paragraph("<b>Secretary of State — Business Ownership Transfer</b>", s["h3"]))
        flow.append(Paragraph(
            "If you are placing a business under your trust, most states require you to file a Change of "
            "Ownership / Change of Responsible Party form with the Secretary of State. This updates the "
            "business registration from your personal name to the trust name. Please contact your Secretary "
            "of State's office to complete this step.",
            s["body"]))

    # Acknowledgments (if any on file)
    acks = case.get("acknowledgments") or {}
    if any(acks.values()):
        flow.append(Spacer(1, 10))
        flow.append(Paragraph("<b>Client Acknowledgments on file</b>", s["h3"]))
        flow.append(_kv_table([
            ("Legal disclosure acknowledged", "Yes" if acks.get("disclosure_ack") else "No"),
            ("State law variance acknowledged", "Yes" if acks.get("state_laws_ack") else "No"),
            ("Notarization understood", "Yes" if acks.get("notarization_ack") else "No"),
            ("SOS business advisory acknowledged", "Yes" if acks.get("business_sos_ack") else "N/A"),
            ("Review completed by client", "Yes" if acks.get("review_completed_ack") else "No"),
        ], s))

    doc.build(flow, onFirstPage=_header_footer(branding),
              onLaterPages=_header_footer(branding))
    return buf.getvalue()
