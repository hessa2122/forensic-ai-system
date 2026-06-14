from django.contrib import admin
from django.utils import timezone

from .models import AnalysisRequest, DetectionResult, Evidence


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'case', 'uploaded_by', 'status', 'analyzed_at')
    list_filter = ('status', 'analyzed_at')
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
    actions = ['approve_selected_requests', 'reject_selected_requests']

    def approve_selected_requests(self, request, queryset):
        queryset.update(status='approved', reviewed_by=request.user, reviewed_at=timezone.now())
    approve_selected_requests.short_description = 'Approve selected requests'

    def reject_selected_requests(self, request, queryset):
        queryset.update(status='rejected', reviewed_by=request.user, reviewed_at=timezone.now())
    reject_selected_requests.short_description = 'Reject selected requests'
