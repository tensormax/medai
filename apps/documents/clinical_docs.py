"""
Deterministic clinical document PDF generator using fpdf2.

Each document type has its own builder function. The public entry point
is ``generate_document()`` which dispatches to the correct builder.
"""

from datetime import date

from fpdf import FPDF


# Base PDF builder

BLUE = (41, 98, 255)
DARK = (31, 41, 55)
GRAY = (107, 114, 128)
LIGHT_GRAY = (229, 231, 235)
WHITE = (255, 255, 255)


def _safe(text):
    """Sanitise text for Helvetica: replace non-latin chars with ASCII equivalents."""
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "\u00a0": " ",   # non-breaking space
        "\u2013": "-",   # en-dash
        "\u2014": "-",   # em-dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
        "\u2022": "*",   # bullet
        "\u00b0": " deg",# degree sign
        "\u00d7": "x",   # multiplication sign
        "\u00f7": "/",   # division sign
        "\u2264": "<=",  # less-than or equal
        "\u2265": ">=",  # greater-than or equal
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    # Replace any remaining non-latin1 characters with ?
    s = s.encode("latin-1", errors="replace").decode("latin-1")
    return s


class ClinicalPDF(FPDF):
    """FPDF subclass with standard Clinical AI header/footer."""

    def __init__(self, doctor=None, patient=None):
        super().__init__()
        self.clinical_doctor = doctor
        self.clinical_patient = patient
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        # Branding
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*BLUE)
        self.cell(0, 8, "Clinical AI", new_x="LMARGIN", new_y="NEXT")

        # Doctor info
        if self.clinical_doctor:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*DARK)
            self.cell(0, 5, _safe(f"Dr. {self.clinical_doctor.full_name}"), new_x="LMARGIN", new_y="NEXT")
            if self.clinical_doctor.specialization:
                self.cell(0, 5, _safe(self.clinical_doctor.specialization), new_x="LMARGIN", new_y="NEXT")
            if self.clinical_doctor.license_number:
                self.set_text_color(*GRAY)
                self.cell(0, 5, _safe(f"License: {self.clinical_doctor.license_number}"), new_x="LMARGIN", new_y="NEXT")

        # Divider
        self.ln(3)
        self.set_draw_color(*BLUE)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-20)
        self.set_draw_color(*LIGHT_GRAY)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GRAY)
        self.cell(0, 5, f"Generated on: {date.today().strftime('%d/%m/%Y')}  |  Clinical AI", align="C")
        self.cell(0, 5, f"Page {self.page_no()}/{{nb}}", new_x="LMARGIN", new_y="NEXT", align="C")

    # ---- helpers ----

    def document_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*DARK)
        self.cell(0, 10, title.upper(), new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(3)

    def patient_info_block(self, patient):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*DARK)
        self.cell(0, 7, "Patient Information", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*LIGHT_GRAY)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

        fields = [
            ("Name", patient.full_name),
            ("MRN", patient.mrn),
            ("Date of Birth", str(patient.date_of_birth)),
            ("Sex", patient.get_sex_display()),
        ]
        if patient.phone_number:
            fields.append(("Phone", patient.phone_number))
        if patient.address:
            fields.append(("Address", patient.address))

        self.set_font("Helvetica", "", 9)
        for label, value in fields:
            self.set_text_color(*GRAY)
            self.cell(35, 6, _safe(label) + ":")
            self.set_text_color(*DARK)
            self.cell(0, 6, _safe(value), new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def section_heading(self, text):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*DARK)
        self.cell(0, 7, _safe(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*DARK)
        self.multi_cell(0, 5, _safe(text))
        self.ln(2)

    def label_value(self, label, value):
        if not value:
            return
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*GRAY)
        self.cell(40, 6, _safe(label) + ":")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*DARK)
        self.cell(0, 6, _safe(str(value)), new_x="LMARGIN", new_y="NEXT")

    def signature_block(self, doctor):
        self.ln(15)
        self.set_draw_color(*DARK)
        self.line(10, self.get_y(), 80, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*DARK)
        self.cell(0, 5, _safe(f"Dr. {doctor.full_name}"), new_x="LMARGIN", new_y="NEXT")
        if doctor.license_number:
            self.set_text_color(*GRAY)
            self.cell(0, 5, _safe(f"License No: {doctor.license_number}"), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*GRAY)
        self.cell(0, 5, f"Date: {date.today().strftime('%d/%m/%Y')}", new_x="LMARGIN", new_y="NEXT")



# Document builders


def _build_consultation_summary(pdf, patient, doctor, visit, form_data):
    pdf.document_title("Visit / Consultation Summary")
    pdf.patient_info_block(patient)

    pdf.label_value("Consultation Date", visit.started_at.strftime("%d/%m/%Y") if visit else None)
    pdf.label_value("Status", visit.get_status_display() if visit else None)
    pdf.ln(3)

    if visit and visit.summary:
        pdf.section_heading("Summary")
        pdf.body_text(visit.summary)

    # Gather AI and doctor messages from the visit
    if visit:
        messages = visit.messages.order_by("created_at")
        doctor_msgs = [m for m in messages if m.role == "doctor"]
        ai_msgs = [m for m in messages if m.role == "ai"]

        if doctor_msgs:
            pdf.section_heading("Doctor Notes / Questions")
            for m in doctor_msgs:
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(*GRAY)
                pdf.cell(0, 5, m.created_at.strftime("%H:%M"), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*DARK)
                pdf.multi_cell(0, 5, _safe(m.content))
                pdf.ln(2)

        if ai_msgs:
            pdf.section_heading("AI Clinical Notes")
            for m in ai_msgs:
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(*GRAY)
                pdf.cell(0, 5, m.created_at.strftime("%H:%M"), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*DARK)
                pdf.multi_cell(0, 5, _safe(m.content))
                pdf.ln(2)

    # Optional extra sections from form_data
    for section_key, section_label in [
        ("diagnosis", "Assessment / Diagnosis"),
        ("treatment_plan", "Treatment Plan"),
        ("medications", "Medications"),
        ("follow_up", "Follow-up Instructions"),
    ]:
        val = form_data.get(section_key, "").strip()
        if val:
            pdf.section_heading(section_label)
            pdf.body_text(val)

    if not visit:
        pdf.section_heading("Notes")
        pdf.body_text("No visit records available for this patient.")

    pdf.signature_block(doctor)


def _build_prescription(pdf, patient, doctor, _visit, form_data):
    pdf.document_title("Prescription")
    pdf.patient_info_block(patient)

    pdf.label_value("Date", date.today().strftime("%d/%m/%Y"))
    pdf.ln(3)

    medications = form_data.get("medications", [])
    if medications:
        pdf.section_heading("Medications")
        # Table header
        col_widths = [38, 25, 20, 28, 22, 57]
        headers = ["Medication", "Dose", "Route", "Frequency", "Duration", "Instructions"]

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(*WHITE)
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*DARK)
        for med in medications:
            row = [
                med.get("name", ""),
                med.get("dose", ""),
                med.get("route", ""),
                med.get("frequency", ""),
                med.get("duration", ""),
                med.get("instructions", ""),
            ]
            max_lines = max(
                pdf.get_string_width(cell) / (w - 2) + 1
                for cell, w in zip(row, col_widths)
            )
            row_h = max(7, int(max_lines) * 5)
            y_before = pdf.get_y()
            x_start = pdf.get_x()
            for i, cell in enumerate(row):
                pdf.set_xy(x_start + sum(col_widths[:i]), y_before)
                pdf.multi_cell(col_widths[i], 5, cell, border="LR", align="C", max_line_height=5)
            pdf.set_y(max(pdf.get_y(), y_before + row_h))
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    else:
        pdf.section_heading("Medications")
        pdf.body_text("No medications prescribed.")

    notes = form_data.get("notes", "").strip()
    if notes:
        pdf.ln(3)
        pdf.section_heading("Additional Notes")
        pdf.body_text(notes)

    pdf.signature_block(doctor)


def _build_medical_certificate(pdf, patient, doctor, _visit, form_data):
    pdf.document_title("Medical Certificate")
    pdf.patient_info_block(patient)

    diagnosis = _safe(form_data.get("diagnosis", ""))
    start_date = form_data.get("start_date")
    end_date = form_data.get("end_date")
    reason = _safe(form_data.get("reason", ""))
    remarks = _safe(form_data.get("remarks", ""))

    # Convert date objects or ISO strings to display strings
    def _fmt_date(val):
        if not val:
            return ""
        if hasattr(val, "strftime"):
            return val.strftime("%d/%m/%Y")
        try:
            return date.fromisoformat(str(val)).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return str(val)

    start_str = _fmt_date(start_date)
    end_str = _fmt_date(end_date)

    pdf.label_value("Date of Issue", date.today().strftime("%d/%m/%Y"))
    if start_str:
        pdf.label_value("Effective From", start_str)
    if end_str:
        pdf.label_value("Effective Until", end_str)
    pdf.ln(4)

    pdf.section_heading("Certification")
    lines = [
        f"This is to certify that {patient.full_name}",
        f"(MRN: {patient.mrn})",
    ]
    if reason:
        lines[0] += f" was evaluated for the following reason: {reason}."
    else:
        lines[0] += " was evaluated based on the documented clinical information."

    if diagnosis:
        lines.append(f"\nDiagnosis: {diagnosis}")

    if start_str and end_str:
        lines.append(
            f"\nBased on the evaluation, the patient requires medical leave "
            f"from {start_str} to {end_str}."
        )
    elif start_str:
        lines.append(
            f"\nBased on the evaluation, the patient requires medical leave "
            f"from {start_str}."
        )

    pdf.body_text(" ".join(lines))

    if remarks:
        pdf.section_heading("Remarks")
        pdf.body_text(remarks)

    pdf.signature_block(doctor)


def _build_referral_letter(pdf, patient, doctor, _visit, form_data):
    pdf.document_title("Referral Letter")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 6, f"Date: {date.today().strftime('%d/%m/%Y')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.patient_info_block(patient)

    specialist = form_data.get("specialist", "").strip()
    if specialist:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 7, f"Dear Dr. {specialist},", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    reason = form_data.get("reason", "").strip()
    if reason:
        pdf.section_heading("Reason for Referral")
        pdf.body_text(reason)

    diagnosis = form_data.get("diagnosis", "").strip()
    if diagnosis:
        pdf.section_heading("Diagnosis")
        pdf.body_text(diagnosis)

    findings = form_data.get("findings", "").strip()
    if findings:
        pdf.section_heading("Clinical Findings")
        pdf.body_text(findings)

    history = form_data.get("history", "").strip()
    if history:
        pdf.section_heading("Relevant History")
        pdf.body_text(history)

    medications = form_data.get("medications", "").strip()
    if medications:
        pdf.section_heading("Current Medications")
        pdf.body_text(medications)

    purpose = form_data.get("purpose", "").strip()
    if purpose:
        pdf.section_heading("Requested Evaluation")
        pdf.body_text(purpose)

    notes = form_data.get("notes", "").strip()
    if notes:
        pdf.section_heading("Additional Notes")
        pdf.body_text(notes)

    # Closing
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"Dr. {doctor.full_name}", new_x="LMARGIN", new_y="NEXT")
    if doctor.specialization:
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, doctor.specialization, new_x="LMARGIN", new_y="NEXT")
    if doctor.license_number:
        pdf.set_text_color(*GRAY)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, f"Registration No: {doctor.license_number}", new_x="LMARGIN", new_y="NEXT")


# ---------------------------------------------------------------------------
# Registry & public API
# ---------------------------------------------------------------------------

BUILDERS = {
    "consultation_summary": _build_consultation_summary,
    "prescription": _build_prescription,
    "medical_certificate": _build_medical_certificate,
    "referral_letter": _build_referral_letter,
}

DOCUMENT_TYPE_LABELS = {
    "consultation_summary": "Visit / Consultation Summary",
    "prescription": "Prescription",
    "medical_certificate": "Medical Certificate",
    "referral_letter": "Referral Letter",
}


def generate_document(document_type, patient, doctor, visit=None, form_data=None):
    """
    Generate a clinical document PDF.

    Returns (pdf_bytes, title) or raises ValueError for unknown types.
    """
    builder = BUILDERS.get(document_type)
    if not builder:
        raise ValueError(f"Unknown document type: {document_type}")

    form_data = form_data or {}
    pdf = ClinicalPDF(doctor=doctor, patient=patient)
    pdf.alias_nb_pages()
    pdf.add_page()

    builder(pdf, patient, doctor, visit, form_data)

    pdf_bytes = pdf.output()
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("latin-1")

    title = DOCUMENT_TYPE_LABELS.get(document_type, document_type.replace("_", " ").title())
    return pdf_bytes, title
