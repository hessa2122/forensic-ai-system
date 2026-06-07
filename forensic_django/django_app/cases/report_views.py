from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER
from cases.models import Case
from evidence.models import Evidence
from datetime import datetime


def _hex(color):
    try:
        h = color.hexval()
        return h[1:] if h.startswith('#') else h
    except Exception:
        return '8b949e'


@login_required
def download_case_report(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    evidence = Evidence.objects.filter(case=case).order_by('-analyzed_at')
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=forensic_report_' + str(case.case_number) + '.pdf'
    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

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

    ts = ParagraphStyle('T',  fontSize=24, fontName='Helvetica-Bold', textColor=LGT, alignment=TA_CENTER)
    ss = ParagraphStyle('S',  fontSize=10, fontName='Helvetica',      textColor=MUT, alignment=TA_CENTER)
    hs = ParagraphStyle('H',  fontSize=11, fontName='Helvetica-Bold', textColor=ACC, spaceBefore=14, spaceAfter=6)
    ls = ParagraphStyle('L',  fontSize=9,  fontName='Helvetica-Bold', textColor=MUT)
    vs = ParagraphStyle('V',  fontSize=10, fontName='Helvetica',      textColor=LGT)
    ms = ParagraphStyle('M',  fontSize=8,  fontName='Helvetica',      textColor=MUT)
    sl = ParagraphStyle('SL', fontSize=8,  fontName='Helvetica',      textColor=LGT)

    story = []

    ht = Table([[Paragraph('FORENSIC 3D', ts)]], colWidths=[17*cm])
    ht.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),BG),
        ('TOPPADDING',(0,0),(-1,-1),18),
        ('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LEFTPADDING',(0,0),(-1,-1),10),
        ('RIGHTPADDING',(0,0),(-1,-1),10),
        ('LINEBELOW',(0,0),(-1,-1),2,ACC),
    ]))
    story.append(ht)
    story.append(Spacer(1,6))
    story.append(Paragraph('DETECTION &amp; ANALYSIS PLATFORM', ss))
    story.append(Paragraph('OFFICIAL CASE REPORT - CONFIDENTIAL', ss))
    story.append(Spacer(1,14))

    story.append(Paragraph('CASE OVERVIEW', hs))
    story.append(HRFlowable(width='100%', thickness=1, color=BRD))
    story.append(Spacer(1,8))

    priority      = getattr(case, 'priority', 'low') or 'low'
    pri_hex       = _hex(PC.get(priority, MUT))
    status        = getattr(case, 'status', '-') or '-'
    location      = getattr(case, 'location', '-') or '-'
    incident_date = str(getattr(case, 'incident_date', '-') or '-')
    created_at    = case.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(case, 'created_at') else '-'
    created_by    = str(getattr(case, 'created_by', request.user) or request.user)

    od = [
        [Paragraph('Case Number',ls), Paragraph(str(case.case_number),vs), Paragraph('Priority',ls), Paragraph('<font color=#'+pri_hex+'>'+priority.upper()+'</font>',vs)],
        [Paragraph('Title',ls),       Paragraph(str(case.title),vs),       Paragraph('Status',ls),   Paragraph(status.upper(),vs)],
        [Paragraph('Location',ls),    Paragraph(location,vs),              Paragraph('Incident Date',ls), Paragraph(incident_date,vs)],
        [Paragraph('Created By',ls),  Paragraph(created_by,vs),            Paragraph('Created At',ls),    Paragraph(created_at,vs)],
    ]
    ot = Table(od, colWidths=[3.5*cm,5.5*cm,3.5*cm,4.5*cm])
    ot.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,-1),BG),
        ('BACKGROUND',(2,0),(2,-1),BG),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[SRF,SR2]),
        ('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),
        ('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),
        ('GRID',(0,0),(-1,-1),0.5,BRD),
    ]))
    story.append(ot)

    desc = getattr(case, 'description', None)
    if desc:
        story.append(Spacer(1,10))
        story.append(Paragraph('Description', ls))
        dt = Table([[Paragraph(desc,vs)]], colWidths=[17*cm])
        dt.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),SRF),
            ('TOPPADDING',(0,0),(-1,-1),8),
            ('BOTTOMPADDING',(0,0),(-1,-1),8),
            ('LEFTPADDING',(0,0),(-1,-1),8),
            ('RIGHTPADDING',(0,0),(-1,-1),8),
            ('GRID',(0,0),(-1,-1),0.5,BRD),
        ]))
        story.append(dt)

    story.append(Spacer(1,16))
    story.append(Paragraph('EVIDENCE SUMMARY', hs))
    story.append(HRFlowable(width='100%', thickness=1, color=BRD))
    story.append(Spacer(1,8))

    evlist     = list(evidence)
    total      = len(evlist)
    high_count = sum(1 for e in evlist if e.threat_level == 'HIGH')
    med_count  = sum(1 for e in evlist if e.threat_level == 'MEDIUM')

    smdata = [[
        Paragraph('Total Evidence',ls), Paragraph(str(total),vs),
        Paragraph('High Threat',ls),    Paragraph(str(high_count),vs),
        Paragraph('Medium Threat',ls),  Paragraph(str(med_count),vs),
    ]]
    smt = Table(smdata, colWidths=[3*cm,2.5*cm,3*cm,2.5*cm,3*cm,3*cm])
    smt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,0),BG),('BACKGROUND',(2,0),(2,0),BG),('BACKGROUND',(4,0),(4,0),BG),
        ('BACKGROUND',(1,0),(1,0),SRF),('BACKGROUND',(3,0),(3,0),SRF),('BACKGROUND',(5,0),(5,0),SRF),
        ('FONTSIZE',(0,0),(-1,-1),10),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('TOPPADDING',(0,0),(-1,-1),10),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('GRID',(0,0),(-1,-1),0.5,BRD),
    ]))
    story.append(smt)

    if evlist:
        story.append(Spacer(1,16))
        story.append(Paragraph('EVIDENCE DETAILS', hs))
        story.append(HRFlowable(width='100%', thickness=1, color=BRD))
        story.append(Spacer(1,8))

        rows = [[
            Paragraph('#',sl),
            Paragraph('Notes',sl),
            Paragraph('Detections',sl),
            Paragraph('Threat Level',sl),
            Paragraph('Analyzed At',sl),
        ]]

        for i, ev in enumerate(evlist, 1):
            threat  = ev.threat_level or 'LOW'
            tc_hex  = _hex(TC.get(threat, MUT))
            ev_date = ev.analyzed_at.strftime('%Y-%m-%d %H:%M') if ev.analyzed_at else '-'
            notes   = (ev.notes or '-')[:100]
            try:
                dl = ev.get_detections()
                if dl:
                    names = ', '.join(str(d.get('class', d.get('label', '?'))) for d in dl[:5])
                    det_text = str(len(dl)) + ' obj: ' + names
                else:
                    det_text = 'None detected'
            except Exception:
                det_text = '-'

            rows.append([
                Paragraph(str(i), sl),
                Paragraph(notes, sl),
                Paragraph(det_text, sl),
                Paragraph('<font color=#'+tc_hex+'>'+threat+'</font>', sl),
                Paragraph(ev_date, sl),
            ])

        et = Table(rows, colWidths=[0.6*cm,4.5*cm,5.5*cm,2.2*cm,3.2*cm])
        et.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),ACC),
            ('TEXTCOLOR',(0,0),(-1,0),WHT),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,-1),8),
            ('TOPPADDING',(0,0),(-1,-1),6),
            ('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('LEFTPADDING',(0,0),(-1,-1),5),
            ('RIGHTPADDING',(0,0),(-1,-1),5),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[SRF,SR2]),
            ('GRID',(0,0),(-1,-1),0.5,BRD),
            ('ALIGN',(0,0),(0,-1),'CENTER'),
            ('ALIGN',(3,0),(3,-1),'CENTER'),
        ]))
        story.append(et)

    story.append(Spacer(1,24))
    story.append(HRFlowable(width='100%', thickness=1, color=BRD))
    story.append(Spacer(1,6))
    gen_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    story.append(Paragraph('Generated: ' + gen_time + ' | User: ' + str(request.user), ms))
    story.append(Paragraph('CONFIDENTIAL - FOR AUTHORIZED PERSONNEL ONLY', ms))

    doc.build(story)
    return response