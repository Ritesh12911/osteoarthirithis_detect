"""
=============================================================
 OA Detection System — PDF Clinical Report Generator
 SIH 2026 | Problem Statement 26004 | MDoNER
=============================================================
 Generates multi-page clinical PDF reports using ReportLab.
 Falls back to minimal text report if ReportLab unavailable.
=============================================================
"""

import os
import json
from datetime import datetime

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── Try to import ReportLab ────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.lib.colors import (HexColor, white, black, Color)
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Line
    from reportlab.graphics import renderPDF
    from reportlab.graphics.charts.lineplots import LinePlot
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[RPT] ReportLab not available — install with: pip install reportlab")


# ─── COLORS ───────────────────────────────────────────────────────────────────
C_DARK      = HexColor('#0a0f1e') if REPORTLAB_AVAILABLE else None
C_PRIMARY   = HexColor('#22d3ee') if REPORTLAB_AVAILABLE else None
C_SECONDARY = HexColor('#a78bfa') if REPORTLAB_AVAILABLE else None
C_SUCCESS   = HexColor('#10b981') if REPORTLAB_AVAILABLE else None
C_WARNING   = HexColor('#f59e0b') if REPORTLAB_AVAILABLE else None
C_DANGER    = HexColor('#f43f5e') if REPORTLAB_AVAILABLE else None
C_BG_LIGHT  = HexColor('#f0f4f8') if REPORTLAB_AVAILABLE else None
C_TEXT_MAIN = HexColor('#1e293b') if REPORTLAB_AVAILABLE else None
C_TEXT_MUTED= HexColor('#64748b') if REPORTLAB_AVAILABLE else None
C_HEADER_BG = HexColor('#0f172a') if REPORTLAB_AVAILABLE else None
C_ROW_ALT   = HexColor('#f8fafc') if REPORTLAB_AVAILABLE else None


def _risk_color(risk_score):
    if not REPORTLAB_AVAILABLE:
        return None
    if risk_score >= 0.75:
        return C_DANGER
    elif risk_score >= 0.55:
        return HexColor('#f97316')
    elif risk_score >= 0.35:
        return C_WARNING
    else:
        return C_SUCCESS


def _risk_label(risk_score):
    if risk_score >= 0.75: return "CRITICAL"
    elif risk_score >= 0.55: return "HIGH"
    elif risk_score >= 0.35: return "MEDIUM"
    else: return "LOW"


# ─── MAIN GENERATOR ───────────────────────────────────────────────────────────

def generate_report(patient_id: str, patient: dict, readings: list,
                    trend: list, clinical_summary: str, diet_plan: dict,
                    exercises: list) -> str:
    """
    Generate a PDF clinical report and return the file path.
    """
    timestamp   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_pid    = patient_id.replace(" ", "_").replace("/", "_")
    filename    = f"OA_Report_{safe_pid}_{timestamp}.pdf"
    pdf_path    = os.path.join(REPORTS_DIR, filename)

    if not REPORTLAB_AVAILABLE:
        return _generate_text_report(pdf_path.replace(".pdf", ".txt"),
                                     patient_id, patient, readings, clinical_summary)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title=f"OA Clinical Report — {patient.get('name', patient_id)}",
        author="OA Detection System · SIH 2026",
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Page 1: Header + Patient Info + Risk ───────────────────────────────────
    story += _build_header(styles, patient_id, patient)
    story += _build_patient_info(styles, patient)
    story += _build_risk_summary(styles, readings)
    story += _build_sensor_table(styles, readings)

    # ── Page 2: Clinical Summary + Trend ──────────────────────────────────────
    story += _build_clinical_summary(styles, clinical_summary)
    if trend:
        story += _build_trend_section(styles, trend)

    # ── Page 3: Diet Plan ─────────────────────────────────────────────────────
    if diet_plan:
        story += _build_diet_plan(styles, diet_plan)

    # ── Page 4: Exercise Protocol ──────────────────────────────────────────────
    if exercises:
        story += _build_exercises(styles, exercises[:6])

    # ── Footer disclaimer ──────────────────────────────────────────────────────
    story += _build_disclaimer(styles)

    doc.build(story)
    print(f"[RPT] Report generated: {pdf_path}")
    return pdf_path


# ─── SECTION BUILDERS ─────────────────────────────────────────────────────────

def _build_header(styles, patient_id, patient):
    elements = []

    # Full-width header banner (simulated with a table)
    header_data = [[
        Paragraph(
            '<font color="#22d3ee"><b>OA</b></font><font color="#a78bfa">Detect</font> <font color="#94a3b8">3D</font>',
            ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=22, textColor=white, alignment=TA_LEFT)
        ),
        Paragraph(
            '<font color="#94a3b8">Clinical Screening Report</font><br/>'
            '<font color="#64748b" size="9">SIH 2026 · PS-26004 · MDoNER · North Eastern Region</font>',
            ParagraphStyle('hdr2', fontName='Helvetica', fontSize=10, textColor=white, alignment=TA_RIGHT)
        )
    ]]
    header_table = Table(header_data, colWidths=[90*mm, 80*mm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), C_HEADER_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (0, -1), 14),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 14),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6*mm))

    # Report metadata line
    gen_time = datetime.utcnow().strftime("%d %B %Y, %H:%M UTC")
    elements.append(Paragraph(
        f'<font color="#64748b">Report Generated: {gen_time} &nbsp;|&nbsp; Patient ID: {patient_id} &nbsp;|&nbsp; System: ESP32-S3 N16R8</font>',
        ParagraphStyle('meta', fontName='Helvetica', fontSize=8, textColor=C_TEXT_MUTED, alignment=TA_CENTER)
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=HexColor('#e2e8f0')))
    elements.append(Spacer(1, 4*mm))
    return elements


def _build_patient_info(styles, patient):
    elements = []
    elements.append(Paragraph(
        '● Patient Demographics',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 3*mm))

    comorbid_list = patient.get('comorbidities', '') or 'None reported'
    oa_grade = patient.get('oa_grade', 'Unknown')
    grade_colors = {'0': '#10b981', '1': '#f59e0b', '2': '#f97316', '3': '#f43f5e', '4': '#7f1d1d', 'Unknown': '#64748b'}
    gc = grade_colors.get(str(oa_grade), '#64748b')

    data = [
        ["Full Name",        patient.get('name', '—'),
         "Date of Birth (Age)", f"{patient.get('age', '?')} years"],
        ["Gender",           patient.get('gender', '—'),
         "BMI",              f"{patient.get('bmi', '?')} kg/m²"],
        ["OA Grade (KL)",    f"Grade {oa_grade}",
         "Comorbidities",    comorbid_list],
        ["Clinical Notes",   patient.get('notes', '—'), "", ""],
    ]

    col_widths = [30*mm, 55*mm, 40*mm, 45*mm]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (0, -1), HexColor('#f1f5f9')),
        ('BACKGROUND',  (2, 0), (2, -2), HexColor('#f1f5f9')),
        ('FONTNAME',    (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',    (2, 0), (2, -2), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 9),
        ('TEXTCOLOR',   (0, 0), (0, -1), C_TEXT_MUTED),
        ('TEXTCOLOR',   (2, 0), (2, -2), C_TEXT_MUTED),
        ('TOPPADDING',  (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('GRID',        (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('SPAN',        (1, 3), (3, 3)),
        ('SPAN',        (2, 3), (3, 3)),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))
    return elements


def _build_risk_summary(styles, readings):
    elements = []
    elements.append(Paragraph(
        '● AI Risk Assessment',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 3*mm))

    if not readings:
        elements.append(Paragraph("No readings available.", styles['Normal']))
        return elements

    latest  = readings[-1]
    risk    = latest.get("risk_score", 0)
    level   = _risk_label(risk)
    rc      = _risk_color(risk)
    n_read  = len(readings)
    avg_risk= sum(r.get("risk_score", 0) for r in readings) / max(n_read, 1)
    oa_ct   = sum(1 for r in readings if r.get("label") == "Early_OA")

    # Risk score big display
    risk_data = [[
        Paragraph(
            f'<b><font size="28" color="{rc.hexval() if hasattr(rc,"hexval") else "#f43f5e"}">{risk:.0%}</font></b><br/>'
            f'<font size="11" color="#64748b"><b>OA RISK SCORE</b></font>',
            ParagraphStyle('rsk', fontName='Helvetica', fontSize=10, alignment=TA_CENTER)
        ),
        Table([
            [Paragraph('<b>Risk Level</b>', ParagraphStyle('rl', fontName='Helvetica-Bold', fontSize=9, textColor=C_TEXT_MUTED)),
             Paragraph(f'<b>{level}</b>', ParagraphStyle('rlv', fontName='Helvetica-Bold', fontSize=9))],
            [Paragraph('<b>Avg Risk (Session)</b>', ParagraphStyle('ar', fontName='Helvetica-Bold', fontSize=9, textColor=C_TEXT_MUTED)),
             Paragraph(f'{avg_risk:.1%}', ParagraphStyle('arv', fontName='Helvetica', fontSize=9))],
            [Paragraph('<b>Total Readings</b>', ParagraphStyle('tr', fontName='Helvetica-Bold', fontSize=9, textColor=C_TEXT_MUTED)),
             Paragraph(f'{n_read}', ParagraphStyle('trv', fontName='Helvetica', fontSize=9))],
            [Paragraph('<b>OA-positive Readings</b>', ParagraphStyle('op', fontName='Helvetica-Bold', fontSize=9, textColor=C_TEXT_MUTED)),
             Paragraph(f'{oa_ct} ({oa_ct/max(n_read,1):.0%})', ParagraphStyle('opv', fontName='Helvetica', fontSize=9))],
            [Paragraph('<b>ML Method</b>', ParagraphStyle('mm', fontName='Helvetica-Bold', fontSize=9, textColor=C_TEXT_MUTED)),
             Paragraph(latest.get("method", "Ensemble"), ParagraphStyle('mmv', fontName='Helvetica', fontSize=9))],
        ], colWidths=[40*mm, 60*mm]),
    ]]
    rt = Table(risk_data, colWidths=[40*mm, 130*mm])
    rt.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',  (0, 0), (0, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('BOX',    (0, 0), (-1, -1), 1, HexColor('#e2e8f0')),
        ('GRID',   (0, 0), (-1, -1), 0.5, HexColor('#f1f5f9')),
    ]))
    elements.append(rt)
    elements.append(Spacer(1, 5*mm))
    return elements


def _build_sensor_table(styles, readings):
    elements = []
    elements.append(Paragraph(
        '● Sensor Readings Summary',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 3*mm))

    if not readings:
        return elements

    # Average last 10 readings
    recent = readings[-10:] if len(readings) >= 10 else readings
    avg = lambda key: round(sum(r.get(key, 0) for r in recent) / len(recent), 3)

    headers = ["Metric", "Current", "Session Avg", "Normal Ref", "Status"]
    rows = [headers]

    metrics = [
        ("Joint Temp (°C)",  readings[-1].get("joint_temp_c", 0), avg("joint_temp_c"), "32–34",
         "⚠ High" if readings[-1].get("joint_temp_c", 0) > 34.5 else "✓ Normal"),
        ("Crepitus Score",   readings[-1].get("crepitus_score", 0), avg("crepitus_score"), "< 0.10",
         "⚠ High" if readings[-1].get("crepitus_score", 0) > 0.30 else "✓ Normal"),
        ("Thermal Asymmetry",readings[-1].get("temp_asymmetry", 0), avg("temp_asymmetry"), "< 0.50°C",
         "⚠ High" if readings[-1].get("temp_asymmetry", 0) > 0.5 else "✓ Normal"),
        ("Flexion ROM (°)",  readings[-1].get("flex_angle_deg", 0), avg("flex_angle_deg"), "90–130",
         "⚠ Low" if readings[-1].get("flex_angle_deg", 0) < 80 else "✓ Normal"),
        ("Gait Symmetry",    readings[-1].get("step_symmetry", 0), avg("step_symmetry"), "0.90–1.00",
         "⚠ Low" if readings[-1].get("step_symmetry", 0) < 0.85 else "✓ Normal"),
        ("Gyro ROM (°)",     readings[-1].get("gyro_range_deg", 0), avg("gyro_range_deg"), "90–120",
         "⚠ Low" if readings[-1].get("gyro_range_deg", 0) < 70 else "✓ Normal"),
        ("Audio RMS",        readings[-1].get("audio_rms", 0), avg("audio_rms"), "< 0.03",
         "⚠ High" if readings[-1].get("audio_rms", 0) > 0.04 else "✓ Normal"),
        ("Flex Stiffness",   readings[-1].get("flex_stiffness", 0), avg("flex_stiffness"), "< 0.20",
         "⚠ High" if readings[-1].get("flex_stiffness", 0) > 0.30 else "✓ Normal"),
    ]

    for m in metrics:
        rows.append([m[0], str(m[1]), str(m[2]), m[3], m[4]])

    col_widths = [50*mm, 28*mm, 28*mm, 28*mm, 36*mm]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0), C_HEADER_BG),
        ('TEXTCOLOR',   (0, 0), (-1, 0), white),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, -1), 8.5),
        ('ALIGN',       (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_ROW_ALT]),
        ('GRID',        (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('TOPPADDING',  (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (0, -1), 8),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))
    return elements


def _build_clinical_summary(styles, summary_text):
    elements = []
    elements.append(Paragraph(
        '● Clinical Interpretation',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 3*mm))
    body_style = ParagraphStyle(
        'body', fontName='Helvetica', fontSize=9.5,
        textColor=C_TEXT_MAIN, leading=14, spaceAfter=6
    )
    for para in summary_text.split('\n\n'):
        if para.strip():
            elements.append(Paragraph(para.strip().replace('\n', ' '), body_style))
    elements.append(Spacer(1, 4*mm))
    return elements


def _build_trend_section(styles, trend):
    elements = []
    elements.append(Paragraph(
        '● 30-Day Risk Progression Trend',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 3*mm))

    if len(trend) < 2:
        elements.append(Paragraph("Insufficient data for trend analysis.", styles['Normal']))
        return elements

    # Simple trend table
    headers = ["Date", "Avg Risk", "Max Risk", "Avg Temp (°C)", "Avg ROM (°)", "Readings"]
    rows = [headers]
    for t in trend[-14:]:
        rows.append([
            t.get("date", ""),
            f"{t.get('avg_risk', 0):.1%}",
            f"{t.get('max_risk', 0):.1%}",
            f"{t.get('avg_temp', 0):.1f}",
            f"{t.get('avg_rom', 0):.0f}",
            str(t.get("n_readings", 0)),
        ])

    col_widths = [28*mm, 25*mm, 25*mm, 30*mm, 25*mm, 20*mm]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), C_HEADER_BG),
        ('TEXTCOLOR',    (0, 0), (-1, 0), white),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 8),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, C_ROW_ALT]),
        ('GRID',         (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))
    return elements


def _build_diet_plan(styles, diet):
    elements = []
    elements.append(Paragraph(
        '● Personalised Dietary Recommendations',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 2*mm))

    summary = diet.get("summary", "")
    if summary:
        elements.append(Paragraph(summary,
            ParagraphStyle('body', fontName='Helvetica', fontSize=9, textColor=C_TEXT_MAIN, leading=13)))
    elements.append(Spacer(1, 3*mm))

    # Beneficial foods
    elements.append(Paragraph('▶ Recommended Anti-Inflammatory Foods:',
        ParagraphStyle('sh', fontName='Helvetica-Bold', fontSize=10, textColor=C_SUCCESS)))
    elements.append(Spacer(1, 2*mm))

    bene_data = [["Food", "Clinical Benefit", "Daily Quantity"]]
    for f in diet.get("beneficial_foods", [])[:6]:
        bene_data.append([
            f.get("food", ""), f.get("reason", ""), f.get("quantity", "—")
        ])
    bt = Table(bene_data, colWidths=[42*mm, 90*mm, 38*mm])
    bt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#064e3b')),
        ('TEXTCOLOR',  (0, 0), (-1, 0), white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#f0fdf4')]),
        ('GRID',       (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
    ]))
    elements.append(bt)
    elements.append(Spacer(1, 3*mm))

    # Foods to avoid
    elements.append(Paragraph('✕ Foods to Avoid:',
        ParagraphStyle('sh', fontName='Helvetica-Bold', fontSize=10, textColor=C_DANGER)))
    elements.append(Spacer(1, 2*mm))
    avoid_data = [["Food", "Why to Avoid"]]
    for f in diet.get("avoid_foods", [])[:5]:
        avoid_data.append([f.get("food", ""), f.get("reason", "")])
    at = Table(avoid_data, colWidths=[50*mm, 120*mm])
    at.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#7f1d1d')),
        ('TEXTCOLOR',  (0, 0), (-1, 0), white),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#fff1f2')]),
        ('GRID',       (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
    ]))
    elements.append(at)
    elements.append(Spacer(1, 3*mm))

    # 7-day meal plan
    elements.append(Paragraph('📅 7-Day Sample Meal Plan:',
        ParagraphStyle('sh', fontName='Helvetica-Bold', fontSize=10, textColor=C_SECONDARY)))
    elements.append(Spacer(1, 2*mm))
    meal_data = [["Day", "Breakfast", "Lunch", "Dinner", "Snack"]]
    for day in diet.get("meal_plan", []):
        meal_data.append([
            day.get("day", ""), day.get("breakfast", ""), day.get("lunch", ""),
            day.get("dinner", ""), day.get("snack", "")
        ])
    mt = Table(meal_data, colWidths=[12*mm, 42*mm, 42*mm, 42*mm, 32*mm])
    mt.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), HexColor('#1e1b4b')),
        ('TEXTCOLOR',    (0, 0), (-1, 0), white),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#f5f3ff')]),
        ('GRID',         (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 3*mm))

    # Calorie note
    cal = diet.get("calorie_target", 1800)
    elements.append(Paragraph(
        f'⚡ Daily Calorie Target: <b>{cal} kcal</b> &nbsp; | &nbsp; '
        f'💧 Hydration: {diet.get("hydration_tip", "Drink 8-10 glasses/day")}',
        ParagraphStyle('note', fontName='Helvetica', fontSize=8.5, textColor=C_TEXT_MUTED, leading=12)
    ))
    elements.append(Spacer(1, 4*mm))
    return elements


def _build_exercises(styles, exercises):
    elements = []
    elements.append(Paragraph(
        '● Rehabilitation Exercise Protocol',
        ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=12, textColor=C_PRIMARY)
    ))
    elements.append(Spacer(1, 3*mm))

    diff_colors = {'Low': '#10b981', 'Medium': '#f59e0b', 'High': '#f43f5e'}

    for ex in exercises:
        dc = diff_colors.get(ex.get('difficulty', 'Low'), '#10b981')
        ex_data = [[
            Paragraph(
                f'<b>{ex.get("emoji","🏋️")} {ex.get("name","Exercise")}</b> &nbsp; '
                f'<font color="{dc}"><b>[{ex.get("difficulty","Low")}]</b></font> &nbsp; '
                f'<font color="#64748b">{ex.get("type","").upper()}</font>',
                ParagraphStyle('exh', fontName='Helvetica-Bold', fontSize=9.5, textColor=C_TEXT_MAIN)
            )
        ], [
            Table([[
                Paragraph(f'<b>Duration:</b> {ex.get("duration","—")}',
                    ParagraphStyle('ed', fontName='Helvetica', fontSize=8.5, textColor=C_TEXT_MUTED)),
                Paragraph(f'<b>Reps:</b> {ex.get("reps","—")}',
                    ParagraphStyle('er', fontName='Helvetica', fontSize=8.5, textColor=C_TEXT_MUTED)),
                Paragraph(f'<b>Sets:</b> {ex.get("sets","—")}',
                    ParagraphStyle('es', fontName='Helvetica', fontSize=8.5, textColor=C_TEXT_MUTED)),
            ]], colWidths=[55*mm, 55*mm, 55*mm])
        ], [
            Paragraph(ex.get("instructions",""),
                ParagraphStyle('ei', fontName='Helvetica', fontSize=8.5, textColor=C_TEXT_MAIN, leading=12))
        ], [
            Paragraph(f'<i>Why: {ex.get("rationale","")}</i> &nbsp; ⚠ {ex.get("precautions","")}',
                ParagraphStyle('ep', fontName='Helvetica-Oblique', fontSize=8, textColor=C_TEXT_MUTED))
        ]]
        et = Table(ex_data, colWidths=[170*mm])
        et.setStyle(TableStyle([
            ('BOX',          (0, 0), (-1, -1), 0.8, HexColor('#e2e8f0')),
            ('BACKGROUND',   (0, 0), (-1, 0), HexColor('#f8fafc')),
            ('TOPPADDING',   (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
            ('LEFTPADDING',  (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(et)
        elements.append(Spacer(1, 3*mm))

    return elements


def _build_disclaimer(styles):
    elements = []
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#e2e8f0')))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph(
        '⚕ <b>MEDICAL DISCLAIMER:</b> This report is generated by an AI-assisted wearable screening system '
        'and is intended for clinical decision support purposes only. It does NOT constitute a medical diagnosis. '
        'All findings must be reviewed and confirmed by a qualified orthopedic specialist. '
        'Do not alter treatment plans based solely on this report.',
        ParagraphStyle('disc', fontName='Helvetica', fontSize=7.5, textColor=C_TEXT_MUTED,
                       leading=11, borderPad=4, backColor=HexColor('#fef9c3'))
    ))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        f'OA Detection System · SIH 2026 · PS-26004 · MDoNER · Report generated {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC',
        ParagraphStyle('footer', fontName='Helvetica', fontSize=7, textColor=C_TEXT_MUTED, alignment=TA_CENTER)
    ))
    return elements


def _generate_text_report(path, patient_id, patient, readings, summary):
    """Fallback plain text report when ReportLab is not available."""
    lines = [
        "=" * 60,
        "  OA Detection System — Clinical Report",
        f"  Patient: {patient.get('name', patient_id)}",
        f"  Generated: {datetime.utcnow().isoformat()} UTC",
        "=" * 60,
        "",
        f"Patient ID:   {patient_id}",
        f"Age:          {patient.get('age', '?')}",
        f"Gender:       {patient.get('gender', '?')}",
        f"BMI:          {patient.get('bmi', '?')}",
        f"OA Grade:     {patient.get('oa_grade', 'Unknown')}",
        f"Comorbidities:{patient.get('comorbidities', 'None')}",
        "",
        "--- CLINICAL SUMMARY ---",
        summary,
        "",
        "--- LATEST READINGS ---",
    ]
    if readings:
        r = readings[-1]
        lines += [
            f"Risk Score:   {r.get('risk_score', 0):.1%}",
            f"Joint Temp:   {r.get('joint_temp_c', 0):.1f}°C",
            f"Crepitus:     {r.get('crepitus_score', 0):.3f}",
            f"Flex ROM:     {r.get('flex_angle_deg', 0):.0f}°",
            f"Gait Sym:     {r.get('step_symmetry', 0):.2f}",
        ]
    lines += [
        "",
        "DISCLAIMER: Screening tool only. Consult orthopedic specialist.",
        "=" * 60,
    ]
    txt_path = path
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[RPT] Text report generated: {txt_path}")
    return txt_path
