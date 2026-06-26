from django.shortcuts import render


def home(request):
    return render(request, "home.html")

def landing_page(request):
    return render(request, "home.html")