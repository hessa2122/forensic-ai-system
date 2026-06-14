"""
accounts/views.py
Handles: user registration, login/logout, home, and
         all admin-side user management + audit log views.
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import UserRegistrationForm, UserProfileEditForm
from .models import UserProfile, AuditLog, log_action


# ─── Helpers ──────────────────────────────────────────────────

def _is_admin(user):
    return user.is_authenticated and user.is_staff


def _approved_required(view_func):
    """Redirect unapproved users to a waiting page."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_staff:
            try:
                if not request.user.profile.is_approved:
                    return render(request, 'accounts/pending_approval.html')
            except UserProfile.DoesNotExist:
                return render(request, 'accounts/pending_approval.html')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── Public views ─────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            log_action(user, 'register', target=user.username, request=request)
            return render(request, 'accounts/register_success.html', {'username': user.username})
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = 'Invalid username or password.'
        elif not user.is_active:
            error = 'Your account has been disabled.'
        elif not user.is_staff:
            try:
                if not user.profile.is_approved:
                    error = 'Your account is awaiting admin approval.'
                    log_action(user, 'login', target='blocked-pending', request=request)
                    return render(request, 'registration/login.html', {'error': error})
            except UserProfile.DoesNotExist:
                error = 'Your account is awaiting admin approval.'
                return render(request, 'registration/login.html', {'error': error})
        if user and error is None:
            login(request, user)
            # update last_active
            try:
                user.profile.last_active = timezone.now()
                user.profile.save(update_fields=['last_active'])
            except UserProfile.DoesNotExist:
                pass
            log_action(user, 'login', request=request)
            return redirect('home')
    return render(request, 'registration/login.html', {'error': error})


def logout_view(request):
    if request.user.is_authenticated:
        log_action(request.user, 'logout', request=request)
        logout(request)
    return redirect('login')


# ─── User dashboard / home ────────────────────────────────────

@login_required
@_approved_required
def home(request):
    return render(request, 'index.html')


# ─── Admin: user management ───────────────────────────────────

@login_required
@user_passes_test(_is_admin)
def admin_users(request):
    """List all registered (non-superuser) users."""
    profiles = UserProfile.objects.select_related('user', 'approved_by').filter(
        user__is_superuser=False
    ).order_by('-created_at')
    return render(request, 'accounts/admin_users.html', {
        'profiles': profiles,
        'pending_count': profiles.filter(is_approved=False).count(),
    })


@login_required
@user_passes_test(_is_admin)
def admin_user_detail(request, user_id):
    """View / edit a single user."""
    target_user = get_object_or_404(User, id=user_id, is_superuser=False)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if request.method == 'POST':
        form = UserProfileEditForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            log_action(request.user, 'role_changed',
                       target=target_user.username,
                       details=f"role={form.cleaned_data['role']}",
                       request=request)
            return redirect('admin_users')
    else:
        form = UserProfileEditForm(instance=profile)

    audit_entries = AuditLog.objects.filter(user=target_user).order_by('-timestamp')[:20]
    return render(request, 'accounts/admin_user_detail.html', {
        'target_user': target_user,
        'profile': profile,
        'form': form,
        'audit_entries': audit_entries,
    })


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def admin_approve_user(request, user_id):
    """Approve a pending user account."""
    target_user = get_object_or_404(User, id=user_id, is_superuser=False)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.is_approved = True
    profile.approved_by = request.user
    profile.approved_at = timezone.now()
    profile.save()
    log_action(request.user, 'approved',
               target=target_user.username, request=request)
    return redirect(request.POST.get('next', 'admin_users'))


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def admin_revoke_user(request, user_id):
    """Revoke approval (user can no longer log in)."""
    target_user = get_object_or_404(User, id=user_id, is_superuser=False)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.is_approved = False
    profile.save()
    log_action(request.user, 'role_changed',
               target=target_user.username, details='approval revoked', request=request)
    return redirect('admin_users')


@login_required
@user_passes_test(_is_admin)
@require_http_methods(['POST'])
def admin_delete_user(request, user_id):
    """Delete a non-superuser account."""
    target_user = get_object_or_404(User, id=user_id, is_superuser=False)
    username = target_user.username
    target_user.delete()
    log_action(request.user, 'role_changed',
               target=username, details='account deleted', request=request)
    return redirect('admin_users')


@login_required
@user_passes_test(_is_admin)
def admin_audit_log(request):
    """Full audit trail view."""
    entries = AuditLog.objects.select_related('user').order_by('-timestamp')[:200]
    return render(request, 'accounts/admin_audit_log.html', {'entries': entries})


# ─── API: stats for admin dashboard ──────────────────────────

@login_required
@user_passes_test(_is_admin)
def api_admin_user_stats(request):
    total    = UserProfile.objects.filter(user__is_superuser=False).count()
    pending  = UserProfile.objects.filter(user__is_superuser=False, is_approved=False).count()
    approved = total - pending
    return JsonResponse({'total': total, 'pending': pending, 'approved': approved})
