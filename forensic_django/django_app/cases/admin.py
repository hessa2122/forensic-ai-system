from django.contrib import admin

from .models import Case, Report, SystemService


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('case_number', 'title', 'status', 'priority', 'assigned_to', 'created_by', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('case_number', 'title')
    list_editable = ('status', 'priority', 'assigned_to')


@admin.register(SystemService)
class SystemServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'service_type', 'is_enabled', 'created_at', 'updated_at')
    list_filter = ('service_type', 'is_enabled')
    search_fields = ('name', 'description')
    list_editable = ('is_enabled',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('generated_at', 'report_title', 'case', 'evidence', 'generated_by', 'checksum_sha256')
    list_filter = ('generated_at',)
    search_fields = ('report_title', 'case__case_number', 'generated_by__username', 'checksum_sha256')
    readonly_fields = ('generated_at', 'checksum_sha256')
