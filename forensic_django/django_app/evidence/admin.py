from django.contrib import admin
from .models import AnalysisRequest, DetectionResult, Evidence
from .views import _run_approved_request
from .services import request_workflow


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'case', 'uploaded_by', 'status', 'uploaded_at', 'analyzed_at')
    list_filter = ('status', 'uploaded_at', 'analyzed_at')
    search_fields = ('original_filename', 'case__case_number', 'uploaded_by__username')


@admin.register(DetectionResult)
class DetectionResultAdmin(admin.ModelAdmin):
    list_display = ('evidence', 'scene_type', 'evidence_count', 'analyzed_at')
    search_fields = ('evidence__original_filename', 'scene_summary')


@admin.register(AnalysisRequest)
class AnalysisRequestAdmin(admin.ModelAdmin):
    list_display = ('evidence', 'requested_by', 'status', 'requested_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('status',)
    search_fields = ('evidence__original_filename', 'requested_by__username')
    actions = ['approve_selected_requests', 'approve_and_run_selected_requests', 'reject_selected_requests']

    def approve_selected_requests(self, request, queryset):
        for analysis_request in queryset:
            try:
                request_workflow.approve_request(analysis_request.id, request.user, request=request)
            except Exception as exc:
                self.message_user(request, f'Request {analysis_request.pk} could not be approved: {exc}', level='ERROR')
    approve_selected_requests.short_description = 'Approve selected requests'

    def approve_and_run_selected_requests(self, request, queryset):
        for analysis_request in queryset:
            try:
                analysis_request = request_workflow.approve_request(analysis_request.id, request.user, request=request)
                _run_approved_request(analysis_request, actor=request.user)
            except Exception as exc:
                self.message_user(request, f'Request {analysis_request.pk} failed: {exc}', level='ERROR')
    approve_and_run_selected_requests.short_description = 'Approve and run selected requests'

    def reject_selected_requests(self, request, queryset):
        for analysis_request in queryset:
            try:
                request_workflow.reject_request(analysis_request.id, request.user, 'Rejected by admin.', request=request)
            except Exception as exc:
                self.message_user(request, f'Request {analysis_request.pk} could not be rejected: {exc}', level='ERROR')
    reject_selected_requests.short_description = 'Reject selected requests'
