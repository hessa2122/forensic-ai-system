"""
cases/views.py
Case management — create, list, detail, delete.
"""
from rest_framework.views    import APIView
from rest_framework.response import Response
from rest_framework          import status
from django.shortcuts        import get_object_or_404
from django.db.models        import Count, Q

from .models import Case


class CaseListView(APIView):

    def get(self, request):
        cases = Case.objects.annotate(
            evidence_count=Count('evidence_set'),
            weapon_count  =Count('evidence_set',
                                  filter=Q(evidence_set__weapons_found=True))
        )
        data = [{
            'id':             c.pk,
            'title':          c.title,
            'case_number':    c.case_number,
            'status':         c.status,
            'priority':       c.priority,
            'priority_color': c.get_priority_color(),
            'location':       c.location,
            'incident_date':  str(c.incident_date) if c.incident_date else None,
            'evidence_count': c.evidence_count,
            'weapon_count':   c.weapon_count,
            'created_at':     c.created_at.isoformat(),
        } for c in cases]
        return Response(data)

    def post(self, request):
        case = Case.objects.create(
            title         = request.data.get('title', 'Untitled Case'),
            case_number   = request.data.get('case_number', f'CASE-{Case.objects.count()+1:04d}'),
            description   = request.data.get('description', ''),
            location      = request.data.get('location', ''),
            incident_date = request.data.get('incident_date') or None,
            status        = request.data.get('status', 'open'),
            priority      = request.data.get('priority', 'medium'),
        )
        return Response({
            'id':          case.pk,
            'title':       case.title,
            'case_number': case.case_number,
            'status':      case.status,
            'priority':    case.priority,
        }, status=status.HTTP_201_CREATED)


class CaseDetailView(APIView):

    def get(self, request, pk):
        c = get_object_or_404(Case, pk=pk)
        return Response({
            'id':           c.pk,
            'title':        c.title,
            'case_number':  c.case_number,
            'description':  c.description,
            'location':     c.location,
            'incident_date':str(c.incident_date) if c.incident_date else None,
            'status':       c.status,
            'priority':     c.priority,
            'priority_color':c.get_priority_color(),
            'created_at':   c.created_at.isoformat(),
        })

    def delete(self, request, pk):
        get_object_or_404(Case, pk=pk).delete()
        return Response({'message': 'Case deleted.'})


class DashboardStatsView(APIView):
    """GET /api/stats/ — summary for dashboard."""

    def get(self, request):
        from evidence.models import Evidence
        from reconstruction.models import SceneReconstruction

        return Response({
            'total_cases':        Case.objects.count(),
            'open_cases':         Case.objects.filter(status='open').count(),
            'total_evidence':     Evidence.objects.count(),
            'weapons_detected':   Evidence.objects.filter(weapons_found=True).count(),
            'reconstructions':    SceneReconstruction.objects.filter(success=True).count(),
            'critical_cases':     Case.objects.filter(priority='critical').count(),
            'risk_distribution': {
                'none':     Evidence.objects.filter(overall_risk='none').count(),
                'low':      Evidence.objects.filter(overall_risk='low').count(),
                'moderate': Evidence.objects.filter(overall_risk='moderate').count(),
                'high':     Evidence.objects.filter(overall_risk='high').count(),
                'critical': Evidence.objects.filter(overall_risk='critical').count(),
            }
        })