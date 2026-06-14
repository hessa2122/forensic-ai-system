"""
accounts/forms.py
Registration, login, and profile management forms.
"""
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile


class UserRegistrationForm(UserCreationForm):
    first_name   = forms.CharField(max_length=30,  required=True,  label='First Name')
    last_name    = forms.CharField(max_length=30,  required=True,  label='Last Name')
    email        = forms.EmailField(required=True, label='Email Address')
    role         = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, label='Role')
    department   = forms.CharField(max_length=100, required=False, label='Department')
    phone        = forms.CharField(max_length=20,  required=False, label='Phone Number')
    badge_number = forms.CharField(max_length=50,  required=False, label='Badge / ID Number')

    class Meta:
        model  = User
        fields = ('username', 'first_name', 'last_name', 'email',
                  'password1', 'password2', 'role', 'department', 'phone', 'badge_number')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.email      = self.cleaned_data['email']
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role         = self.cleaned_data['role']
            profile.department   = self.cleaned_data.get('department', '')
            profile.phone        = self.cleaned_data.get('phone', '')
            profile.badge_number = self.cleaned_data.get('badge_number', '')
            profile.is_approved  = False   # requires admin approval
            profile.save()
        return user


class UserProfileEditForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30,  required=False)
    last_name  = forms.CharField(max_length=30,  required=False)
    email      = forms.EmailField(required=False)

    class Meta:
        model  = UserProfile
        fields = ('role', 'department', 'phone', 'badge_number', 'notes')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            u = self.instance.user
            self.fields['first_name'].initial = u.first_name
            self.fields['last_name'].initial  = u.last_name
            self.fields['email'].initial      = u.email

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            u = profile.user
            u.first_name = self.cleaned_data.get('first_name', u.first_name)
            u.last_name  = self.cleaned_data.get('last_name',  u.last_name)
            u.email      = self.cleaned_data.get('email',      u.email)
            u.save()
            profile.save()
        return profile
