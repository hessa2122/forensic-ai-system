"""
cases/views.py
Role-aware case management with audit logging.
Admin can see/manage ALL cases.
Investigators/Analysts see only their own assigned cases.
"""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views import View

from .models import Case, SystemService
from evidence.models import DetectionResult, Evidence
from accounts.models import log_action
from accounts.permissions import can_manage_cases, can_manage_services, case_access_q, is_approved_user, is_system_admin
from accounts.services import notify_user


def _case_filter(user):
    """Admin sees everything; others see only cases they created or are assigned to."""
    return case_access_q(user)


class CaseListView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not is_approved_user(request.user):
            return JsonResponse({'error': 'Account pending admin approval'}, status=403)

        cases = Case.objects.filter(_case_filter(request.user)).annotate(
            evidence_count=Count('evidence_items')
        ).order_by('-created_at')

        PRIORITY_COLORS = {
            'low':      '#22c55e',
            'medium':   '#f59e0b',
            'high':     '#ef4444',
            'critical': '#8b5cf6',
        }

        data = []
        for case in cases:
            data.append({
                'id':             case.id,
                'case_number':    case.case_number,
                'title':          case.title,
                'status':         case.status,
                'priority':       case.priority,
                'priority_color': PRIORITY_COLORS.get(case.priority, '#8b949e'),
                'location':       case.location,
                'created_at':     str(case.created_at),
                'evidence_count': case.evidence_count,
                'assigned_to':    str(case.assigned_to) if case.assigned_to else None,
                'created_by':     str(case.created_by) if case.created_by else None,
            })
        return JsonResponse(data, safe=False)

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not can_manage_cases(request.user):
            return JsonResponse({'error': 'Admin access required'}, status=403)

        try:
            body = json.loads(request.body)
        except Exception:
            body = {}

        case_number = body.get('case_number') or f"CASE-{uuid.uuid4().hex[:8].upper()}"
        while Case.objects.filter(case_number=case_number).exists():
            case_number = f"CASE-{uuid.uuid4().hex[:8].upper()}"

        # Resolve assigned_to
        assigned_to = None
        assigned_id = body.get('assigned_to_id')
        if assigned_id and request.user.is_staff:
            from django.contrib.auth.models import User
            try:
                assigned_to = User.objects.get(id=assigned_id)
            except User.DoesNotExist:
                pass

        case = Case.objects.create(
            case_number=case_number,
            title=body.get('title', 'New Case'),
            description=body.get('description', ''),
            location=body.get('location', ''),
            incident_date=body.get('incident_date') or None,
            status=body.get('status', 'open'),
            priority=body.get('priority', 'medium'),
            created_by=request.user,
            assigned_to=assigned_to,
        )
        log_action(request.user, 'case_created', target=f'Case #{case.case_number}')
        if case.assigned_to:
            notify_user(
                case.assigned_to,
                f"Admin assigned you to case {case.case_number}.",
                'case',
                case,
                title='Case assigned',
            )
        return JsonResponse({'id': case.id, 'case_number': case.case_number, 'title': case.title})


class CaseDetailView(View):
    def get(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not is_approved_user(request.user):
            return JsonResponse({'error': 'Account pending admin approval'}, status=403)
        try:
            case = Case.objects.get(_case_filter(request.user), pk=pk)
        except Case.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        evidence_data = []
        for e in case.evidence_items.all():
            detection = getattr(e, 'detectionresult', None)
            evidence_data.append({
                'id':          e.id,
                'image':       e.file.url if e.file else '',
                'status':      e.status,
                'analyzed_at': str(e.analyzed_at),
                'summary':     detection.scene_summary if detection else '',
                'filename':    e.original_filename,
            })
        return JsonResponse({
            'id':          case.id,
            'case_number': case.case_number,
            'title':       case.title,
            'status':      case.status,
            'priority':    case.priority,
            'location':    case.location,
            'description': case.description,
            'assigned_to': str(case.assigned_to) if case.assigned_to else None,
            'evidence':    evidence_data,
        })

    def patch(self, request, pk):
        """Admin can update a case."""
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not can_manage_cases(request.user):
            return JsonResponse({'error': 'Admin access required'}, status=403)
        try:
            case = Case.objects.get(_case_filter(request.user), pk=pk)
        except Case.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)
        try:
            body = json.loads(request.body)
        except Exception:
            body = {}
        for field in ('title', 'description', 'location', 'status', 'priority'):
            if field in body:
                setattr(case, field, body[field])
        case.save()
        log_action(request.user, 'case_updated', target=f'Case #{case.case_number}')
        if case.assigned_to:
            notify_user(
                case.assigned_to,
                f"Admin updated case {case.case_number}.",
                'case',
                case,
                title='Case updated',
            )
        return JsonResponse({'ok': True})

    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not can_manage_cases(request.user):
            return JsonResponse({'error': 'Admin access required'}, status=403)
        try:
            case = Case.objects.get(_case_filter(request.user), pk=pk)
        except Case.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)
        cn = case.case_number
        case.delete()
        log_action(request.user, 'case_deleted', target=f'Case #{cn}')
        return JsonResponse({'deleted': True})


class StatsView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not is_approved_user(request.user):
            return JsonResponse({'error': 'Account pending admin approval'}, status=403)

        from reconstruction.models import SceneReconstruction
        case_qs = Case.objects.filter(_case_filter(request.user))

        none_count = medium_count = high_count = 0
        evidence_qs = Evidence.objects.filter(case__in=case_qs)
        detection_qs = DetectionResult.objects.filter(evidence__in=evidence_qs).only('detections_json')
        for result in detection_qs:
            try:
                detections = json.loads(result.detections_json or '[]')
            except json.JSONDecodeError:
                detections = []
            levels = {d.get('forensic_significance', 'low').lower() for d in detections}
            if 'high'   in levels: high_count   += 1
            elif 'medium' in levels: medium_count += 1
            else:                    none_count   += 1

        return JsonResponse({
            'total_cases':      case_qs.count(),
            'open_cases':       case_qs.filter(status='open').count(),
            'total_evidence':   evidence_qs.count(),
            'high_threat':      high_count,
            'medium_threat':    medium_count,
            'weapons_detected': high_count,
            'reconstructions':  SceneReconstruction.objects.filter(case__in=case_qs, success=True).count(),
            'critical_cases':   case_qs.filter(priority='critical').count(),
            'risk_distribution': {
                'none':     none_count,
                'low':      0,
                'moderate': medium_count,
                'high':     high_count,
                'critical': case_qs.filter(priority='critical').count(),
            },
        })


class SystemServiceView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        if not can_manage_services(request.user):
            return JsonResponse({'error': 'Admin access required'}, status=403)
        services = SystemService.objects.all()
        return JsonResponse([{
            'id': service.id,
            'name': service.name,
            'service_type': service.service_type,
            'is_enabled': service.is_enabled,
            'config': service.config,
            'description': service.description,
            'updated_at': str(service.updated_at),
        } for service in services], safe=False)

    def post(self, request):
        if not can_manage_services(request.user):
            return JsonResponse({'error': 'Admin access required'}, status=403)
        try:
            body = json.loads(request.body)
        except Exception:
            body = {}
        service_id = body.get('id')
        name = body.get('name')
        try:
            service = SystemService.objects.get(id=service_id) if service_id else SystemService.objects.get(name=name)
        except SystemService.DoesNotExist:
            return JsonResponse({'error': 'Service not found'}, status=404)
        service.is_enabled = body.get('is_enabled', not service.is_enabled)
        service.save(update_fields=['is_enabled', 'updated_at'])
        return JsonResponse({'id': service.id, 'name': service.name, 'is_enabled': service.is_enabled})
