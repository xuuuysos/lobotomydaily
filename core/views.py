from django.shortcuts import render


def index(request):
    return render(request, 'core/index.html')


def register(request):
    return render(request, 'core/register.html')
