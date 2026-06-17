"""
cases/report_views.py
Professional PDF case report generator for Forensic AI System.
Includes case overview, evidence summary, uploaded evidence images,
AI detection findings, threat levels, and audit logging.
"""
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from datetime import datetime
from html import escape
import json
import os

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage, KeepTogether, PageBreak,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

from cases.models import Case
from evidence.models import Evidence
from accounts.models import log_action


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def _safe(value, default="-"):
    """Return an HTML-safe string for ReportLab Paragraph."""
    if value is None or value == "":
        return default
    return escape(str(value))


def _hex_str(color_obj):
    """Convert a ReportLab HexColor to plain hex string without '#'."""
    try:
        h = color_obj.hexval()
        return h[1:] if h.startswith("#") else h
    except Exception:
        return "94a3b8"


def _fmt_dt(value, fmt="%Y-%m-%d %H:%M"):
    try:
        return value.strftime(fmt) if value else "-"
    except Exception:
        return "-"


def _rl_image(file_field, max_w, max_h):
    """Return a ReportLab Image flowable sized to fit max_w x max_h."""
    if not file_field:
        return None
    try:
        path = file_field.path
    except Exception:
        return None
    if not os.path.isfile(path):
        return None

    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as img:
            orig_w, orig_h = img.size
        ratio = min(max_w / orig_w, max_h / orig_h, 1.0)
        return RLImage(path, width=orig_w * ratio, height=orig_h * ratio)
    except Exception:
        try:
            return RLImage(path, width=max_w, height=max_h)
        except Exception:
            return None


def _get_detections(ev):
    """Return detection list for an Evidence object."""
    try:
        raw = ev.detectionresult.detections_json or "[]"
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _get_scene_summary(ev):
    try:
        return ev.detectionresult.scene_summary or "-"
    except Exception:
        return "-"


def _det_label(det):
    return str(det.get("class") or det.get("label") or det.get("name") or "Unknown")


def _evidence_level(ev):
    detections = _get_detections(ev)
    levels = {str(d.get("forensic_significance", "low")).upper() for d in detections}
    labels = {_det_label(d).lower() for d in detections}

    # Strong keyword fallback for common forensic objects.
    high_keywords = {"gun", "knife", "weapon", "pistol", "blood", "bloodstain"}
    if "HIGH" in levels or any(k in label for label in labels for k in high_keywords):
        return "HIGH"
    if "MEDIUM" in levels:
        return "MEDIUM"
    return "LOW"


def _evidence_detection_text(ev, limit=6):
    detections = _get_detections(ev)
    if not detections:
        return "No AI detections recorded"
    names = []
    for d in detections[:limit]:
        label = _det_label(d)
        conf = d.get("confidence")
        try:
            conf_txt = f" ({float(conf) * 100:.0f}%)" if conf is not None else ""
        except Exception:
            conf_txt = ""
        names.append(f"{label}{conf_txt}")
    extra = "" if len(detections) <= limit else f" + {len(detections) - limit} more"
    return f"{len(detections)} object(s): " + ", ".join(names) + extra


def _make_info_table(data, col_widths, label_bg, row_bg1, row_bg2, border):
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), label_bg),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [row_bg1, row_bg2]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.45, border),
    ]))
    return tbl


def _on_page(canvas, doc):
    """Draw dark background, footer, and page number."""
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#020617"))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)

    # Top thin line
    canvas.setStrokeColor(colors.HexColor("#0ea5e9"))
    canvas.setLineWidth(1)
    canvas.line(1.6 * cm, height - 1.25 * cm, width - 1.6 * cm, height - 1.25 * cm)

    # Footer
    canvas.setStrokeColor(colors.HexColor("#1e293b"))
    canvas.line(1.6 * cm, 1.25 * cm, width - 1.6 * cm, 1.25 * cm)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(1.7 * cm, 0.85 * cm, "CONFIDENTIAL - For authorized forensic personnel only")
    canvas.drawRightString(width - 1.7 * cm, 0.85 * cm, f"Page {doc.page}")
    canvas.restoreState()


# -----------------------------------------------------------------------------
# Main PDF report view
# -----------------------------------------------------------------------------

@login_required
def download_case_report(request, case_id):
    case = get_object_or_404(Case, id=case_id)

    if not REPORTLAB_OK:
        return HttpResponse(
            "PDF reporting requires the optional 'reportlab' package.",
            status=503,
            content_type="text/plain",
        )

    evidence_qs = Evidence.objects.filter(case=case).order_by("-analyzed_at")
    evlist = list(evidence_qs)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f"attachment; filename=forensic_report_{case.case_number}.pdf"
    )

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=1.55 * cm,
        leftMargin=1.55 * cm,
        topMargin=1.65 * cm,
        bottomMargin=1.65 * cm,
    )

    # Professional dark forensic palette
    BG = colors.HexColor("#020617")
    PANEL = colors.HexColor("#0f172a")
    PANEL2 = colors.HexColor("#111827")
    PANEL3 = colors.HexColor("#1e293b")
    BORDER = colors.HexColor("#334155")
    ACCENT = colors.HexColor("#38bdf8")
    BLUE = colors.HexColor("#2563eb")
    TEXT = colors.HexColor("#f8fafc")
    MUTED = colors.HexColor("#94a3b8")
    GREEN = colors.HexColor("#22c55e")
    AMBER = colors.HexColor("#f59e0b")
    RED = colors.HexColor("#ef4444")
    PURPLE = colors.HexColor("#8b5cf6")
    WHITE = colors.white

    LEVEL_COLOR = {"LOW": GREEN, "MEDIUM": AMBER, "HIGH": RED}
    PRIORITY_COLOR = {
        "low": GREEN,
        "medium": AMBER,
        "high": RED,
        "critical": PURPLE,
    }

    # Paragraph styles
    title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=TEXT, alignment=TA_LEFT)
    sub = ParagraphStyle("Sub", fontName="Helvetica", fontSize=9, leading=12, textColor=MUTED, alignment=TA_LEFT)
    center_small = ParagraphStyle("CenterSmall", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED, alignment=TA_CENTER)
    section = ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=ACCENT, spaceBefore=12, spaceAfter=6)
    label = ParagraphStyle("Label", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED)
    value = ParagraphStyle("Value", fontName="Helvetica", fontSize=9, leading=12, textColor=TEXT)
    value_bold = ParagraphStyle("ValueBold", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=TEXT)
    muted = ParagraphStyle("Muted", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED)
    body = ParagraphStyle("Body", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT)
    tiny = ParagraphStyle("Tiny", fontName="Helvetica", fontSize=7, leading=9, textColor=MUTED)
    right = ParagraphStyle("Right", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=TEXT, alignment=TA_RIGHT)

    story = []

    # ------------------------------------------------------------------
    # Header / cover block
    # ------------------------------------------------------------------
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    priority = getattr(case, "priority", "low") or "low"
    priority_color = _hex_str(PRIORITY_COLOR.get(priority, MUTED))

    header_data = [[
        Paragraph("FORENSIC AI<br/><font color='#38bdf8'>CASE REPORT</font>", title),
        Paragraph(
            f"Report ID: FR-{_safe(case.case_number)}<br/>Generated: {_safe(generated_at)}<br/>Generated By: {_safe(request.user)}",
            right,
        ),
    ]]
    header = Table(header_data, colWidths=[10.6 * cm, 6.2 * cm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 1, BLUE),
        ("LINEBELOW", (0, 0), (-1, -1), 2, ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))
    story.append(Paragraph("OFFICIAL DIGITAL FORENSIC ANALYSIS REPORT - CONFIDENTIAL", center_small))
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------------
    # Executive summary cards
    # ------------------------------------------------------------------
    high_count = sum(1 for ev in evlist if _evidence_level(ev) == "HIGH")
    med_count = sum(1 for ev in evlist if _evidence_level(ev) == "MEDIUM")
    low_count = sum(1 for ev in evlist if _evidence_level(ev) == "LOW")
    total_detections = sum(len(_get_detections(ev)) for ev in evlist)

    summary_data = [[
        Paragraph("TOTAL EVIDENCE", label), Paragraph(str(len(evlist)), value_bold),
        Paragraph("AI DETECTIONS", label), Paragraph(str(total_detections), value_bold),
        Paragraph("HIGH RISK", label), Paragraph(f"<font color='#{_hex_str(RED)}'>{high_count}</font>", value_bold),
    ], [
        Paragraph("MEDIUM RISK", label), Paragraph(f"<font color='#{_hex_str(AMBER)}'>{med_count}</font>", value_bold),
        Paragraph("LOW RISK", label), Paragraph(f"<font color='#{_hex_str(GREEN)}'>{low_count}</font>", value_bold),
        Paragraph("CASE PRIORITY", label), Paragraph(f"<font color='#{priority_color}'>{_safe(priority.upper())}</font>", value_bold),
    ]]
    summary_table = Table(summary_data, colWidths=[2.8 * cm, 2.6 * cm, 2.8 * cm, 2.6 * cm, 2.8 * cm, 3.2 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL2),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PANEL2, PANEL]),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)

    # ------------------------------------------------------------------
    # Case overview
    # ------------------------------------------------------------------
    story.append(Spacer(1, 14))
    story.append(Paragraph("1. CASE OVERVIEW", section))
    story.append(HRFlowable(width="100%", thickness=0.7, color=BORDER))
    story.append(Spacer(1, 7))

    status = getattr(case, "status", "-") or "-"
    location = getattr(case, "location", "-") or "-"
    incident_date = getattr(case, "incident_date", None)
    created_at = getattr(case, "created_at", None)
    created_by = getattr(case, "created_by", None) or request.user

    overview_data = [
        [Paragraph("Case Number", label), Paragraph(_safe(case.case_number), value),
         Paragraph("Status", label), Paragraph(_safe(str(status).upper()), value)],
        [Paragraph("Case Title", label), Paragraph(_safe(case.title), value),
         Paragraph("Priority", label), Paragraph(f"<font color='#{priority_color}'>{_safe(priority.upper())}</font>", value_bold)],
        [Paragraph("Location", label), Paragraph(_safe(location), value),
         Paragraph("Incident Date", label), Paragraph(_safe(incident_date), value)],
        [Paragraph("Created By", label), Paragraph(_safe(created_by), value),
         Paragraph("Created At", label), Paragraph(_safe(_fmt_dt(created_at)), value)],
    ]
    overview = Table(overview_data, colWidths=[3.2 * cm, 5.3 * cm, 3.2 * cm, 5.1 * cm])
    overview.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PANEL3),
        ("BACKGROUND", (2, 0), (2, -1), PANEL3),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [PANEL, PANEL2]),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(overview)

    description = getattr(case, "description", None)
    if description:
        story.append(Spacer(1, 9))
        desc_box = Table([[Paragraph("Case Description", label)], [Paragraph(_safe(description), body)]], colWidths=[16.8 * cm])
        desc_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PANEL3),
            ("BACKGROUND", (0, 1), (-1, 1), PANEL),
            ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.append(desc_box)

    # ------------------------------------------------------------------
    # Evidence index table
    # ------------------------------------------------------------------
    story.append(Spacer(1, 14))
    story.append(Paragraph("2. EVIDENCE INDEX", section))
    story.append(HRFlowable(width="100%", thickness=0.7, color=BORDER))
    story.append(Spacer(1, 7))

    if evlist:
        index_data = [[
            Paragraph("#", label), Paragraph("Filename", label), Paragraph("Threat", label),
            Paragraph("Detections", label), Paragraph("Analyzed At", label),
        ]]
        for idx, ev in enumerate(evlist, 1):
            threat = _evidence_level(ev)
            threat_color = _hex_str(LEVEL_COLOR.get(threat, MUTED))
            index_data.append([
                Paragraph(str(idx), value),
                Paragraph(_safe(ev.original_filename), value),
                Paragraph(f"<font color='#{threat_color}'>{threat}</font>", value_bold),
                Paragraph(str(len(_get_detections(ev))), value),
                Paragraph(_safe(_fmt_dt(getattr(ev, "analyzed_at", None))), value),
            ])
        index_table = Table(index_data, colWidths=[1 * cm, 7 * cm, 2.4 * cm, 2.4 * cm, 4 * cm])
        index_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PANEL3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PANEL, PANEL2]),
            ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(index_table)
    else:
        empty_box = Table([[Paragraph("No evidence records are available for this case.", body)]], colWidths=[16.8 * cm])
        empty_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PANEL),
            ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(empty_box)

    # ------------------------------------------------------------------
    # Evidence details with images
    # ------------------------------------------------------------------
    if evlist:
        story.append(Spacer(1, 14))
        story.append(Paragraph("3. DETAILED EVIDENCE ANALYSIS", section))
        story.append(HRFlowable(width="100%", thickness=0.7, color=BORDER))
        story.append(Spacer(1, 7))

        for idx, ev in enumerate(evlist, 1):
            threat = _evidence_level(ev)
            threat_color = _hex_str(LEVEL_COLOR.get(threat, MUTED))
            detections = _get_detections(ev)
            scene_summary = _get_scene_summary(ev)
            uploader = getattr(ev, "uploaded_by", None) or "-"
            notes = getattr(ev, "notes", None) or "-"
            file_size = getattr(ev, "file_size", None)
            file_size_text = f"{file_size:,} bytes" if file_size else "-"

            evidence_header = Table([[
                Paragraph(f"Evidence #{idx}: {_safe(ev.original_filename)}", value_bold),
                Paragraph(f"<font color='#{threat_color}'>{threat} RISK</font>", right),
            ]], colWidths=[12.2 * cm, 4.6 * cm])
            evidence_header.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PANEL3),
                ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
                ("LINEBELOW", (0, 0), (-1, -1), 1.1, LEVEL_COLOR.get(threat, MUTED)),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))

            image = _rl_image(ev.file, max_w=7.2 * cm, max_h=5.7 * cm)
            if image:
                img_box = Table([[image], [Paragraph("Uploaded evidence image", tiny)]], colWidths=[7.4 * cm])
                img_box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), PANEL2),
                    ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
            else:
                img_box = Table([[Paragraph("Evidence image not available", muted)]], colWidths=[7.4 * cm])
                img_box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), PANEL2),
                    ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 40),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 40),
                ]))

            meta_data = [
                [Paragraph("Uploaded By", label), Paragraph(_safe(uploader), value)],
                [Paragraph("Analyzed At", label), Paragraph(_safe(_fmt_dt(getattr(ev, "analyzed_at", None))), value)],
                [Paragraph("File Size", label), Paragraph(_safe(file_size_text), value)],
                [Paragraph("Detection Summary", label), Paragraph(_safe(_evidence_detection_text(ev)), value)],
                [Paragraph("Investigator Notes", label), Paragraph(_safe(notes[:240]), value)],
                [Paragraph("Scene Summary", label), Paragraph(_safe(scene_summary[:360]), value)],
            ]
            meta_table = _make_info_table(meta_data, [3.0 * cm, 6.2 * cm], PANEL3, PANEL, PANEL2, BORDER)

            combined = Table([[img_box, meta_table]], colWidths=[7.5 * cm, 9.3 * cm])
            combined.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))

            block_items = [evidence_header, combined]

            # Detection table for each evidence item
            if detections:
                det_data = [[
                    Paragraph("Object", label), Paragraph("Confidence", label),
                    Paragraph("Significance", label), Paragraph("Source", label),
                ]]
                for d in detections[:10]:
                    sig = str(d.get("forensic_significance", "low")).upper()
                    sig_color = _hex_str(LEVEL_COLOR.get(sig, MUTED))
                    conf = d.get("confidence")
                    try:
                        conf_text = f"{float(conf) * 100:.1f}%" if conf is not None else "-"
                    except Exception:
                        conf_text = "-"
                    det_data.append([
                        Paragraph(_safe(_det_label(d)), value),
                        Paragraph(_safe(conf_text), value),
                        Paragraph(f"<font color='#{sig_color}'>{_safe(sig)}</font>", value_bold),
                        Paragraph(_safe(d.get("source", "AI Engine")), value),
                    ])
                det_table = Table(det_data, colWidths=[5.2 * cm, 3.2 * cm, 4 * cm, 4.4 * cm])
                det_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), PANEL3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PANEL, PANEL2]),
                    ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                block_items.extend([Spacer(1, 6), det_table])

            block_items.append(Spacer(1, 11))
            story.append(KeepTogether(block_items))

            # Prevent very long reports from making one huge unreadable page chunk.
            if idx % 2 == 0 and idx != len(evlist):
                story.append(PageBreak())

    # ------------------------------------------------------------------
    # Final declaration
    # ------------------------------------------------------------------
    story.append(Spacer(1, 18))
    story.append(Paragraph("4. REPORT DECLARATION", section))
    story.append(HRFlowable(width="100%", thickness=0.7, color=BORDER))
    story.append(Spacer(1, 7))

    declaration = (
        "This report is generated from the Forensic AI System using stored case records, "
        "uploaded evidence files, and AI-assisted detection output. The detected objects and "
        "risk indicators should be reviewed and verified by authorized forensic personnel before "
        "being used for final investigative conclusions."
    )
    declaration_box = Table([[Paragraph(declaration, body)]], colWidths=[16.8 * cm])
    declaration_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
    ]))
    story.append(declaration_box)

    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Generated: {_safe(generated_at)} | User: {_safe(request.user)}", muted))
    story.append(Paragraph("CONFIDENTIAL - FOR AUTHORIZED PERSONNEL ONLY", muted))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    log_action(
        request.user,
        "report_download",
        target=f"Case #{case.case_number}",
        request=request,
    )

    return response
