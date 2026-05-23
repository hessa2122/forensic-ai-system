import json
import uuid
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from .models import Case
from evidence.models import Evidence


@method_decorator(csrf_exempt, name="dispatch")
class CaseListView(View):
    def get(self, request):
        cases = Case.objects.annotate(
            evidence_count=Count("evidence_items")
        ).order_by("-created_at")

        PRIORITY_COLORS = {
            "low":      "#22c55e",
            "medium":   "#f59e0b",
            "high":     "#ef4444",
            "critical": "#8b5cf6",
        }

        data = []
        for case in cases:
            data.append({
                "id":             case.id,
                "case_number":    case.case_number,
                "title":          case.title,
                "status":         case.status,
                "priority":       case.priority,
                "priority_color": PRIORITY_COLORS.get(case.priority, "#8b949e"),
                "location":       case.location,
                "created_at":     str(case.created_at),
                "evidence_count": case.evidence_count,
            })
        # Return plain array so frontend can do cases.slice(0,5)
        return JsonResponse(data, safe=False)

    def post(self, request):
        try:
            body = json.loads(request.body)
        except Exception:
            body = {}
        case_number = body.get("case_number") or f"CASE-{uuid.uuid4().hex[:8].upper()}"
        while Case.objects.filter(case_number=case_number).exists():
            case_number = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        case = Case.objects.create(
            case_number=case_number,
            title=body.get("title", "New Case"),
            description=body.get("description", ""),
            location=body.get("location", ""),
            status=body.get("status", "open"),
            priority=body.get("priority", "medium"),
        )
        return JsonResponse({"id": case.id, "case_number": case.case_number, "title": case.title})


@method_decorator(csrf_exempt, name="dispatch")
class CaseDetailView(View):
    def get(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)
        evidence_data = []
        for e in case.evidence_items.all():
            evidence_data.append({
                "id":           e.id,
                "image":        str(e.image),
                "threat_level": e.threat_level,
                "analyzed_at":  str(e.analyzed_at),
                "summary":      e.get_summary(),
            })
        return JsonResponse({
            "id":          case.id,
            "case_number": case.case_number,
            "title":       case.title,
            "status":      case.status,
            "evidence":    evidence_data,
        })

    def delete(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)
        case.delete()
        return JsonResponse({"deleted": True})


@method_decorator(csrf_exempt, name="dispatch")
class StatsView(View):
    def get(self, request):
        from reconstruction.models import SceneReconstruction

        # Build risk distribution from evidence threat levels
        none_count   = Evidence.objects.filter(threat_level="LOW").count()
        medium_count = Evidence.objects.filter(threat_level="MEDIUM").count()
        high_count   = Evidence.objects.filter(threat_level="HIGH").count()

        return JsonResponse({
            "total_cases":      Case.objects.count(),
            "open_cases":       Case.objects.filter(status="open").count(),
            "total_evidence":   Evidence.objects.count(),
            "high_threat":      high_count,
            "medium_threat":    medium_count,
            "weapons_detected": high_count,
            "reconstructions":  SceneReconstruction.objects.filter(success=True).count(),
            "critical_cases":   Case.objects.filter(priority="critical").count(),
            "risk_distribution": {
                "none":     none_count,
                "low":      0,
                "moderate": medium_count,
                "high":     high_count,
                "critical": Case.objects.filter(priority="critical").count(),
            },
        })
