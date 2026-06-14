"""
accounts/migrations/0001_initial.py
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id',           models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role',         models.CharField(choices=[('investigator','Investigator'),('analyst','Analyst'),('viewer','Viewer')], default='investigator', max_length=20)),
                ('department',   models.CharField(blank=True, max_length=100)),
                ('phone',        models.CharField(blank=True, max_length=20)),
                ('badge_number', models.CharField(blank=True, max_length=50)),
                ('is_approved',  models.BooleanField(default=False)),
                ('approved_at',  models.DateTimeField(blank=True, null=True)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
                ('last_active',  models.DateTimeField(blank=True, null=True)),
                ('notes',        models.TextField(blank=True)),
                ('user',         models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
                ('approved_by',  models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_users', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action',     models.CharField(choices=[('login','User Login'),('logout','User Logout'),('register','User Registered'),('approved','User Approved'),('role_changed','Role Changed'),('case_created','Case Created'),('case_updated','Case Updated'),('case_deleted','Case Deleted'),('evidence_upload','Evidence Uploaded'),('evidence_delete','Evidence Deleted'),('analysis_run','Analysis Run'),('report_download','Report Downloaded')], max_length=30)),
                ('target',     models.CharField(blank=True, max_length=200)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('details',    models.TextField(blank=True)),
                ('timestamp',  models.DateTimeField(auto_now_add=True)),
                ('user',       models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-timestamp']},
        ),
    ]
