"""FirstHour evidence pack generator (Phase 3).

Builds a clean PDF report a victim can hand to their bank, mobile money
provider or the police. Nothing is stored: the PDF is created in memory
and returned straight to the user.
"""

from datetime import datetime
from typing import Optional

from fpdf import FPDF

LABELS = {
    "en": {
        "title": "Incident Evidence Report",
        "subtitle": "Prepared with FirstHour",
        "generated": "Generated",
        "case_type": "Case type",
        "section_victim": "Reporter details",
        "name": "Full name",
        "phone": "Phone number",
        "section_incident": "Incident details",
        "date": "Date of incident",
        "time": "Time of incident",
        "amount": "Amount lost (KSh)",
        "method": "Payment method",
        "tx_id": "Transaction ID / code",
        "provider": "Bank or provider involved",
        "scammer_phone": "Suspect's phone number",
        "scammer_name": "Suspect's name (as shown)",
        "account": "Account or platform affected",
        "section_story": "What happened",
        "section_actions": "Actions already taken",
        "section_refs": "Reference numbers",
        "bank_ref": "Bank / provider reference",
        "ob": "Police OB number",
        "section_next": "Recommended next steps",
        "section_report_to": "Submit this report to",
        "section_checklist": "Evidence to attach",
        "none": "Not provided",
        "disclaimer": (
            "This document was compiled from information supplied by the reporter. "
            "It is not an official record and has not been verified by FirstHour. "
            "FirstHour provides general guidance, not legal or financial advice."
        ),
        "page": "Page",
    },
    "sw": {
        "title": "Ripoti ya Ushahidi wa Tukio",
        "subtitle": "Imeandaliwa na FirstHour",
        "generated": "Imetengenezwa",
        "case_type": "Aina ya kesi",
        "section_victim": "Taarifa za mwenye kuripoti",
        "name": "Jina kamili",
        "phone": "Nambari ya simu",
        "section_incident": "Maelezo ya tukio",
        "date": "Tarehe ya tukio",
        "time": "Saa ya tukio",
        "amount": "Kiasi kilichopotea (KSh)",
        "method": "Njia ya malipo",
        "tx_id": "Nambari / msimbo wa muamala",
        "provider": "Benki au mtoa huduma husika",
        "scammer_phone": "Nambari ya simu ya mshukiwa",
        "scammer_name": "Jina la mshukiwa",
        "account": "Akaunti au jukwaa lililoathirika",
        "section_story": "Kilichotokea",
        "section_actions": "Hatua zilizokwisha chukuliwa",
        "section_refs": "Nambari za kumbukumbu",
        "bank_ref": "Kumbukumbu ya benki / mtoa huduma",
        "ob": "Nambari ya OB ya polisi",
        "section_next": "Hatua zinazopendekezwa",
        "section_report_to": "Wasilisha ripoti hii kwa",
        "section_checklist": "Ushahidi wa kuambatanisha",
        "none": "Haikutolewa",
        "disclaimer": (
            "Hati hii imeandaliwa kutokana na taarifa zilizotolewa na mwenye kuripoti. "
            "Si rekodi rasmi na haijathibitishwa na FirstHour. "
            "FirstHour hutoa mwongozo wa jumla, si ushauri wa kisheria au kifedha."
        ),
        "page": "Ukurasa",
    },
}

NAVY = (22, 50, 92)
GREY = (90, 90, 90)
LIGHT = (235, 240, 248)


def clean(value: object) -> str:
    """Make text safe for the built-in PDF fonts (Latin-1 only)."""
    text = "" if value is None else str(value)
    for old, new in {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", " ": " ",
    }.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


class EvidencePDF(FPDF):
    def __init__(self, labels: dict):
        super().__init__(format="A4")
        self.labels = labels
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 18, 18)

    def header(self) -> None:
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 26, style="F")
        self.set_xy(18, 7)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 17)
        self.cell(0, 8, clean(self.labels["title"]), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, clean(self.labels["subtitle"]), new_x="LMARGIN", new_y="NEXT")
        self.set_y(32)
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, f"FirstHour  |  {self.labels['page']} {self.page_no()}", align="C")

    def section(self, title: str) -> None:
        self.ln(3)
        self.set_fill_color(*LIGHT)
        self.set_text_color(*NAVY)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 7, " " + clean(title), new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(1)
        self.set_text_color(0, 0, 0)

    def field(self, label: str, value: Optional[str]) -> None:
        shown = clean(value).strip() if value not in (None, "") else self.labels["none"]
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*GREY)
        self.cell(72, 6, clean(label))
        self.set_font("Helvetica", "", 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, shown, new_x="LMARGIN", new_y="NEXT")

    def paragraph(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, clean(text), new_x="LMARGIN", new_y="NEXT")

    def bullets(self, items: list, numbered: bool = False) -> None:
        self.set_font("Helvetica", "", 10)
        for index, item in enumerate(items, start=1):
            marker = f"{index}." if numbered else "-"
            self.cell(7, 5.5, marker)
            self.multi_cell(0, 5.5, clean(item), new_x="LMARGIN", new_y="NEXT")
            self.ln(0.8)


def build_evidence_pdf(report: dict, lang: str, case_title: str = "", plan: Optional[dict] = None) -> bytes:
    """report: dict of user-supplied fields. plan: localized triage plan (optional)."""
    labels = LABELS[lang]
    pdf = EvidencePDF(labels)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, f"{labels['generated']}: {datetime.now().strftime('%d %b %Y, %H:%M')}",
             new_x="LMARGIN", new_y="NEXT")
    if case_title:
        pdf.field(labels["case_type"], case_title)

    pdf.section(labels["section_victim"])
    pdf.field(labels["name"], report.get("victim_name"))
    pdf.field(labels["phone"], report.get("victim_phone"))

    pdf.section(labels["section_incident"])
    pdf.field(labels["date"], report.get("incident_date"))
    pdf.field(labels["time"], report.get("incident_time"))
    amount = report.get("amount_kes")
    pdf.field(labels["amount"], f"{amount:,.2f}" if amount is not None else None)
    pdf.field(labels["method"], report.get("payment_method"))
    pdf.field(labels["tx_id"], report.get("transaction_id"))
    pdf.field(labels["provider"], report.get("bank_or_provider"))
    pdf.field(labels["scammer_phone"], report.get("scammer_phone"))
    pdf.field(labels["scammer_name"], report.get("scammer_name"))
    pdf.field(labels["account"], report.get("account_affected"))

    pdf.section(labels["section_story"])
    pdf.paragraph(report.get("description") or labels["none"])

    actions = [a for a in report.get("actions_taken", []) if a and a.strip()]
    if actions:
        pdf.section(labels["section_actions"])
        pdf.bullets(actions)

    if report.get("bank_reference") or report.get("ob_number"):
        pdf.section(labels["section_refs"])
        pdf.field(labels["bank_ref"], report.get("bank_reference"))
        pdf.field(labels["ob"], report.get("ob_number"))

    if plan:
        pdf.section(labels["section_next"])
        pdf.bullets(plan.get("steps", []), numbered=True)
        pdf.section(labels["section_report_to"])
        pdf.bullets(plan.get("report_to", []))
        pdf.section(labels["section_checklist"])
        pdf.bullets(plan.get("evidence", []))

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4.5, clean(labels["disclaimer"]), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
