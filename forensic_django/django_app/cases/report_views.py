"""
cases/report_views.py
PDF report generator — now includes the uploaded evidence image.
"""
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from datetime import datetime
import json
import os

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage, KeepTogether,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

from cases.models import Case
from evidence.models import Evidence
from accounts.models import log_action


def _hex_str(color_obj):
    """Convert a ReportLab HexColor to plain hex string (no '#')."""
    try:
        h = color_obj.hexval()
        return h[1:] if h.startswith('#') else h
    except Exception:
        return '8b949e'


def _rl_image(file_field, max_w, max_h):
    """
    Return a ReportLab Image flowable sized to fit within max_w × max_h,
    or None if the file doesn't exist / can't be opened.
    """
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
        w = orig_w * ratio
        h = orig_h * ratio
        return RLImage(path, width=w, height=h)
    except Exception:
        # Fallback: let ReportLab scale it itself
        try:
            return RLImage(path, width=max_w, height=max_h)
        except Exception:
            return None


@login_required
def download_case_report(request, case_id):
    case = get_object_or_404(Case, id=case_id)

    if not REPORTLAB_OK:
        return HttpResponse(
            "PDF reporting requires the optional 'reportlab' package.",
            status=503,
            content_type="text/plain",
        )

    evidence_qs = Evidence.objects.filter(case=case).order_by('-analyzed_at')

    # ── Response setup ──────────────────────────────────────────────
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename=forensic_report_{case.case_number}.pdf'
    )
    doc = SimpleDocTemplate(
        response, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    # ── Colour palette ──────────────────────────────────────────────
    BG  = colors.HexColor('#0d1117')
    ACC = colors.HexColor('#3b82f6')
    RED = colors.HexColor('#ef4444')
    GRN = colors.HexColor('#22c55e')
    AMB = colors.HexColor('#f59e0b')
    PUR = colors.HexColor('#8b5cf6')
    LGT = colors.HexColor('#e6edf3')
    MUT = colors.HexColor('#8b949e')
    SRF = colors.HexColor('#161b22')
    SR2 = colors.HexColor('#1c2128')
    BRD = colors.HexColor('#21262d')
    WHT = colors.white

    TC = {'LOW': GRN, 'MEDIUM': AMB, 'HIGH': RED}
    PC = {'low': GRN, 'medium': AMB, 'high': RED, 'critical': PUR}

    # ── Paragraph styles ────────────────────────────────────────────
    ts = ParagraphStyle('T',  fontSize=24, fontName='Helvetica-Bold', textColor=LGT, alignment=TA_CENTER)
    ss = ParagraphStyle('S',  fontSize=10, fontName='Helvetica',      textColor=MUT, alignment=TA_CENTER)
    hs = ParagraphStyle('H',  fontSize=11, fontName='Helvetica-Bold', textColor=ACC, spaceBefore=14, spaceAfter=6)
    ls = ParagraphStyle('L',  fontSize=9,  fontName='Helvetica-Bold', textColor=MUT)
    vs = ParagraphStyle('V',  fontSize=10, fontName='Helvetica',      textColor=LGT)
    ms = ParagraphStyle('M',  fontSize=8,  fontName='Helvetica',      textColor=MUT)
    sl = ParagraphStyle('SL', fontSize=8,  fontName='Helvetica',      textColor=LGT)
    es = ParagraphStyle('E',  fontSize=9,  fontName='Helvetica',      textColor=LGT, leading=13)

    story = []

    # ── Header ──────────────────────────────────────────────────────
    ht = Table([[Paragraph('FORENSIC 3D', ts)]], colWidths=[17 * cm])
    ht.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), BG),
        ('TOPPADDING',   (0, 0), (-1, -1), 18),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
        ('LEFTPADDING',  (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW',    (0, 0), (-1, -1), 2, ACC),
    ]))
    story.append(ht)
    story.append(Spacer(1, 6))
    story.append(Paragraph('DETECTION &amp; ANALYSIS PLATFORM', ss))
    story.append(Paragraph('OFFICIAL CASE REPORT — CONFIDENTIAL', ss))
    story.append(Spacer(1, 14))

    # ── Case overview ────────────────────────────────────────────────
    story.append(Paragraph('CASE OVERVIEW', hs))
    story.append(HRFlowable(width='100%', thickness=1, color=BRD))
    story.append(Spacer(1, 8))

    priority      = getattr(case, 'priority', 'low') or 'low'
    pri_hex       = _hex_str(PC.get(priority, MUT))
    status        = getattr(case, 'status', '-') or '-'
    location      = getattr(case, 'location', '-') or '-'
    incident_date = str(getattr(case, 'incident_date', '-') or '-')
    created_at    = case.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(case, 'created_at') else '-'
    created_by    = str(getattr(case, 'created_by', request.user) or request.user)

    od = [
        [Paragraph('Case Number', ls), Paragraph(str(case.case_number), vs),
         Paragraph('Priority', ls),    Paragraph(f'<font color=#{pri_hex}>{priority.upper()}</font>', vs)],
        [Paragraph('Title', ls),       Paragraph(str(case.title), vs),
         Paragraph('Status', ls),      Paragraph(status.upper(), vs)],
        [Paragraph('Location', ls),    Paragraph(location, vs),
         Paragraph('Incident Date', ls), Paragraph(incident_date, vs)],
        [Paragraph('Created By', ls),  Paragraph(created_by, vs),
         Paragraph('Created At', ls),  Paragraph(created_at, vs)],
    ]
    ot = Table(od, colWidths=[3.5 * cm, 5.5 * cm, 3.5 * cm, 4.5 * cm])
    ot.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, -1), BG),
        ('BACKGROUND',    (2, 0), (2, -1), BG),
        ('ROWBACKGROUNDS',(0, 0), (-1, -1), [SRF, SR2]),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.5, BRD),
    ]))
    story.append(ot)

    desc = getattr(case, 'description', None)
    if desc:
        story.append(Spacer(1, 10))
        story.append(Paragraph('Description', ls))
        dt = Table([[Paragraph(desc, vs)]], colWidths=[17 * cm])
        dt.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), SRF),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('GRID',          (0, 0), (-1, -1), 0.5, BRD),
        ]))
        story.append(dt)

    # ── Evidence summary ─────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(Paragraph('EVIDENCE SUMMARY', hs))
    story.append(HRFlowable(width='100%', thickness=1, color=BRD))
    story.append(Spacer(1, 8))

    evlist = list(evidence_qs)
    total  = len(evlist)

    def evidence_level(ev):
        try:
            detections = json.loads(ev.detectionresult.detections_json or '[]')
        except Exception:
            detections = []
        levels = {d.get('forensic_significance', 'low').upper() for d in detections}
        if 'HIGH'   in levels: return 'HIGH'
        if 'MEDIUM' in levels: return 'MEDIUM'
        return 'LOW'

    high_count = sum(1 for e in evlist if evidence_level(e) == 'HIGH')
    med_count  = sum(1 for e in evlist if evidence_level(e) == 'MEDIUM')

    smdata = [[
        Paragraph('Total Evidence', ls), Paragraph(str(total), vs),
        Paragraph('High Threat', ls),    Paragraph(str(high_count), vs),
        Paragraph('Medium Threat', ls),  Paragraph(str(med_count), vs),
    ]]
    smt = Table(smdata, colWidths=[3 * cm, 2.5 * cm, 3 * cm, 2.5 * cm, 3 * cm, 3 * cm])
    smt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), BG), ('BACKGROUND', (2, 0), (2, 0), BG), ('BACKGROUND', (4, 0), (4, 0), BG),
        ('BACKGROUND', (1, 0), (1, 0), SRF), ('BACKGROUND', (3, 0), (3, 0), SRF), ('BACKGROUND', (5, 0), (5, 0), SRF),
        ('FONTSIZE',   (0, 0), (-1, -1), 10),
        ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('GRID',       (0, 0), (-1, -1), 0.5, BRD),
    ]))
    story.append(smt)

    # ── Evidence details + IMAGES ─────────────────────────────────────
    if evlist:
        story.append(Spacer(1, 16))
        story.append(Paragraph('EVIDENCE DETAILS', hs))
        story.append(HRFlowable(width='100%', thickness=1, color=BRD))
        story.append(Spacer(1, 8))

        for i, ev in enumerate(evlist, 1):
            threat  = evidence_level(ev)
            tc_hex  = _hex_str(TC.get(threat, MUT))
            ev_date = ev.analyzed_at.strftime('%Y-%m-%d %H:%M') if ev.analyzed_at else '-'
            notes   = (ev.notes or '—')[:200]
            uploader = str(ev.uploaded_by) if ev.uploaded_by else '—'

            try:
                dl = json.loads(ev.detectionresult.detections_json or '[]')
                if dl:
                    names    = ', '.join(str(d.get('class', d.get('label', '?'))) for d in dl[:6])
                    det_text = f"{len(dl)} object(s): {names}"
                else:
                    det_text = 'None detected'
                summary = ev.detectionresult.scene_summary or '—'
            except Exception:
                det_text = '—'
                summary  = '—'

            # ── Evidence header row ──
            eh = Table([[
                Paragraph(f'<font color=#3b82f6>Evidence #{i}</font> — {ev.original_filename}', sl),
                Paragraph(f'<font color=#{tc_hex}>{threat}</font>', sl),
            ]], colWidths=[12.5 * cm, 4.5 * cm])
            eh.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, -1), SRF),
                ('TOPPADDING',    (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING',   (0, 0), (-1, -1), 10),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
                ('ALIGN',         (1, 0), (1, 0), 'RIGHT'),
                ('LINEBELOW',     (0, 0), (-1, -1), 0.5, BRD),
            ]))
            story.append(eh)

            # ── Image + meta side by side ─────────────────────────────
            img_flowable = _rl_image(ev.file, max_w=7 * cm, max_h=6 * cm)

            meta_content = [
                [Paragraph('Uploaded By', ls), Paragraph(uploader, es)],
                [Paragraph('Analyzed At', ls), Paragraph(ev_date, es)],
                [Paragraph('File Size',   ls), Paragraph(f'{ev.file_size:,} bytes' if ev.file_size else '—', es)],
                [Paragraph('Detections',  ls), Paragraph(det_text, es)],
                [Paragraph('Notes',       ls), Paragraph(notes, es)],
                [Paragraph('Summary',     ls), Paragraph(summary[:300], es)],
            ]
            meta_table = Table(meta_content, colWidths=[2.8 * cm, 6.2 * cm])
            meta_table.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (0, -1), BG),
                ('ROWBACKGROUNDS',(0, 0), (-1, -1), [SR2, SRF]),
                ('TOPPADDING',    (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING',   (0, 0), (-1, -1), 6),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
                ('GRID',          (0, 0), (-1, -1), 0.4, BRD),
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ]))

            if img_flowable:
                # Image on the left, meta on the right
                img_cell  = Table([[img_flowable]], colWidths=[7.5 * cm])
                img_cell.setStyle(TableStyle([
                    ('BACKGROUND',    (0, 0), (-1, -1), SR2),
                    ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING',    (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('GRID',          (0, 0), (-1, -1), 0.4, BRD),
                ]))
                combined = Table([[img_cell, meta_table]], colWidths=[7.5 * cm, 9.5 * cm])
                combined.setStyle(TableStyle([
                    ('VALIGN',     (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING',(0, 0), (-1, -1), 0),
                    ('RIGHTPADDING',(0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
                ]))
            else:
                # No image — span full width
                combined = meta_table

            story.append(KeepTogether([combined, Spacer(1, 10)]))

    # ── Footer ───────────────────────────────────────────────────────
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width='100%', thickness=1, color=BRD))
    story.append(Spacer(1, 6))
    gen_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    story.append(Paragraph(f'Generated: {gen_time}  |  User: {request.user}', ms))
    story.append(Paragraph('CONFIDENTIAL — FOR AUTHORIZED PERSONNEL ONLY', ms))

    doc.build(story)

    # Audit log
    log_action(request.user, 'report_download',
               target=f'Case #{case.case_number}', request=request)

    return response
