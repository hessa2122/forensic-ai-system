
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.shortcuts import render, redirect

@login_required
def home(request):
    return render(request, 'index.html')

def logout_view(request):
    logout(request)
    return redirect('/login/')