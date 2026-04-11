from .forms import RegisterForm
from django.shortcuts import render, redirect
from django.contrib.auth import login
def get_general_context(request):
    """
    Создает общий контекст
    """
    context = {
        'user': request.user,
        'menu': [
            ['Main page', '/'],
            ['Create new news', '/create_news'],
        ]
    }

    if request.user.is_authenticated:
        context['menu'].append(['Profile', '/profile'])
    else:
        context['menu'].append(['Login', '/accounts/login'])
        context['menu'].append(['Registration', '/accounts/register'])
    return context
def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, "register.html", {"form": form})

def profile(request):
    user = request.user
    context = {
        'user': user
    }
    context.update(get_general_context(request))
    return render(request, "profile.html", context)

from .models import News
from django.utils import timezone
import datetime

def index(request):
    now = timezone.localtime()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    days_data = []
    
    for i in range(7):
        target_start = start_of_today - datetime.timedelta(days=i)
        target_end = target_start + datetime.timedelta(days=1)
        
        daily_news = News.objects.filter(
            parsed_at__gte=target_start,
            parsed_at__lt=target_end
        ).order_by('-parsed_at')
        
        days_data.append({
            'date': target_start,
            'news_list': daily_news,
            'is_today': i == 0
        })

    return render(request, 'core/index.html', {'days_data': days_data})
