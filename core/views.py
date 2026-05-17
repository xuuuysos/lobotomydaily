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
            return redirect('index')
    else:
        form = RegisterForm()
    return render(request, "core/register.html", {"form": form})

def profile(request):
    user = request.user
    context = {
        'user': user
    }
    context.update(get_general_context(request))
    return render(request, "profile.html", context)

from .models import News, Comment
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
import datetime
import json
import urllib.request
import re
from bs4 import BeautifulSoup
import hashlib
from .utils import classify_news
from .ai_utils import ai_get_chat_response

def generate_deterministic_tags(url, title="", body="", seed_id=None):
    return classify_news(title, body, url=url, news_id=seed_id)

def get_top_tags(limit=None):
    from collections import Counter
    from .models import NewsAITags, News
    from .utils import clean_and_deduplicate_tags
    import json
    
    counter = Counter()
    # Get active URLs of existing news to avoid displaying empty/orphan tags
    active_urls = set(News.objects.values_list('url', flat=True))
    
    # Read directly from cache table for active news to avoid N+1 and model instantiation overhead
    for cached in NewsAITags.objects.filter(news_url__in=active_urls):
        try:
            tags = json.loads(cached.tags_json)
            cleaned = clean_and_deduplicate_tags(tags)
            counter.update(cleaned)
        except Exception:
            pass
            
    if limit:
        top = counter.most_common(limit)
        return [tag for tag, count in top]
    
    # Return all unique tags sorted alphabetically
    return sorted(counter.keys())

def index(request):
    from_str = request.GET.get('from')
    to_str = request.GET.get('to')
    
    now = timezone.localtime()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    num_days = 7
    start_point_date = start_of_today.date()

    if from_str and to_str:
        try:
            d_from = datetime.datetime.strptime(from_str, '%Y-%m-%d').date()
            d_to = datetime.datetime.strptime(to_str, '%Y-%m-%d').date()
            
            if d_from > d_to:
                d_from, d_to = d_to, d_from
            
            delta = (d_to - d_from).days
            if delta > 14:
                delta = 14
                d_to = d_from + datetime.timedelta(days=14)
            
            num_days = delta + 1
            start_point_date = d_to
        except ValueError:
            pass

    days_data = []
    
    for i in range(num_days):
        target_date = start_point_date - datetime.timedelta(days=i)
        target_start = timezone.make_aware(datetime.datetime.combine(target_date, datetime.time.min))
        target_end = target_start + datetime.timedelta(days=1)
        
        daily_news = News.objects.filter(
            parsed_at__gte=target_start,
            parsed_at__lt=target_end
        ).order_by('-parsed_at')
        
        # Page loads instantly without waiting for parsing to finish

        days_data.append({
            'date': target_start,
            'news_list': daily_news,
            'is_today': target_date == start_of_today.date()
        })

    # Pre-evaluate tags (using fast offline fallback if uncached) to populate NewsAITags database before get_top_tags()
    for day in days_data:
        for n in day['news_list']:
            _ = n.tags






    top_tags = get_top_tags()
    return render(request, 'core/index.html', {
        'days_data': days_data,
        'top_tags': top_tags,
        'from_date': from_str,
        'to_date': to_str
    })


LENTA_SECTION_PATHS = {
    'Политика':   ['russia', 'world', 'ussr'],
    'Спорт':      ['sport'],
    'Экономика':  ['economics', 'finance', 'realty', 'business'],
    'Технологии': ['internet', 'innovation'],
    'Культура':   ['culture', 'entertainment', 'kino', 'music'],
    'Наука':      ['science', 'space'],
    'Общество':   ['society', 'human_rights', 'life'],
    'Регионы':    ['russia', 'siberia', 'ural'],
}

def _fetch_html(url):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        return ''

_date_html_cache = {}

def _get_date_archive_html(date_obj):
    y, m, d = date_obj.year, date_obj.month, date_obj.day
    key = f'{y}-{m:02d}-{d:02d}'
    if key not in _date_html_cache:
        url = f'https://lenta.ru/{y}/{m:02d}/{d:02d}/'
        _date_html_cache[key] = _fetch_html(url)
    return _date_html_cache.get(key, '')


def _parse_lenta_day_filtered(date_obj, include_labels, exclude_labels):
    """
    Parse lenta.ru/YYYY/MM/DD/ and filter articles by included/excluded tags.
    """
    y, m, d = date_obj.year, date_obj.month, date_obj.day
    html = _get_date_archive_html(date_obj)
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    date_seg = f'{y}/{m:02d}/{d:02d}/'

    articles = []
    seen = set()

    # Pre-calculate set for speed
    include_set = set(include_labels) if include_labels else set()
    exclude_set = set(exclude_labels) if exclude_labels else set()

    for a in soup.find_all('a', href=True):
        href = a['href']
        if date_seg not in href:
            continue
            
        full_url = 'https://lenta.ru' + href if href.startswith('/') else href
        if full_url in seen:
            continue

        title_node = a.find(class_=re.compile(r'title'))
        raw = title_node.get_text(separator=' ') if title_node else a.get_text(separator=' ')
        title = re.sub(r'\s+', ' ', raw).strip()
        title = re.sub(r'\d{2}:\d{2}.*$', '', title).strip()

        if not title or len(title) < 20 or len(title.split()) < 3:
            continue

        # Tag-based filtering
        article_tags = generate_deterministic_tags(full_url, title=title)
        tags_set = set(article_tags)

        # Logic: 
        # 1. If include_set is not empty, must have at least one common tag.
        # 2. If exclude_set is not empty, must have NO common tags.
        
        matches_include = not include_set or not include_set.isdisjoint(tags_set)
        matches_exclude = not exclude_set or exclude_set.isdisjoint(tags_set)

        if not (matches_include and matches_exclude):
            continue

        seen.add(full_url)

        time_str = ''
        time_node = a.find('time') or a.find(class_=re.compile(r'date|time'))
        if time_node:
            mt = re.search(r'(\d{2}):(\d{2})', time_node.get_text(strip=True))
            if mt:
                time_str = f'{mt.group(1)}:{mt.group(2)}'

        articles.append({
            'title': title,
            'url': full_url,
            'time': time_str or f'{d:02d}.{m:02d}',
            'tags': article_tags,
        })

        if len(articles) >= 30:
            break

    return articles


def _extract_article_body(url):
    """Fetch and extract readable text from an article URL."""
    html = _fetch_html(url)
    if not html:
        return ''
    soup = BeautifulSoup(html, 'lxml')
    blocks = []


    body_div = soup.find('div', class_=re.compile(r'topic-body__content|article-text|b-text|content__text'))
    if body_div:
        for p in body_div.find_all('p'):
            t = re.sub(r'\s+', ' ', p.get_text(separator=' ')).strip()
            if t:
                blocks.append(t)


    if not blocks:
        article = soup.find('article')
        if article:
            for p in article.find_all('p'):
                t = re.sub(r'\s+', ' ', p.get_text(separator=' ')).strip()
                if len(t) > 40:
                    blocks.append(t)


    if not blocks:
        for p in soup.find_all('p'):
            t = re.sub(r'\s+', ' ', p.get_text(separator=' ')).strip()
            if len(t) > 100:
                blocks.append(t)

    full = '\n\n'.join(blocks[:8])
    return full or ''


@csrf_exempt
def fetch_article_body(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    url = body.get('url', '').strip()
    if not url:
        return JsonResponse({'error': 'No URL'}, status=400)
    text = _extract_article_body(url)
    return JsonResponse({'body': text})


@csrf_exempt
def fetch_category_news(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    included_tags = body.get('includedTags', [])
    excluded_tags = body.get('excludedTags', [])
    date_strs = body.get('dates', [])

    results = {}

    for date_str in date_strs:
        try:
            date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue

        # Parse with combined inclusive/exclusive logic
        day_articles = _parse_lenta_day_filtered(date_obj, included_tags, excluded_tags)
        results[date_str] = day_articles

    return JsonResponse({'results': results})

@csrf_exempt
def get_comments(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    url = body.get('url', '').strip()
    if not url:
        return JsonResponse({'error': 'No URL provided'}, status=400)

    comments = Comment.objects.filter(news_url=url).select_related('author')
    data = []
    for c in comments:
        data.append({
            'author': c.author.username,
            'text': c.text,
            'created_at': c.created_at.strftime('%d.%m.%Y %H:%M')
        })
    return JsonResponse({'comments': data})

@csrf_exempt
def add_comment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=403)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    url = body.get('url', '').strip()
    text = body.get('text', '').strip()
    
    if not url or not text:
        return JsonResponse({'error': 'URL and text are required'}, status=400)

    comment = Comment.objects.create(
        news_url=url,
        author=request.user,
        text=text
    )

    return JsonResponse({
        'comment': {
            'author': comment.author.username,
            'text': comment.text,
            'created_at': comment.created_at.strftime('%d.%m.%Y %H:%M')
        }
    })

@csrf_exempt
def send_ai_message(request):
    """
    Sends a message to the AI news assistant.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_message = data.get('message', '').strip()
    if not user_message:
        return JsonResponse({'status': 'error', 'message': 'Сообщение не может быть пустым'}, status=400)

    # Get history from session
    messages = request.session.get('ai_messages', [])
    
    # Limit history to avoid huge sessions
    if len(messages) > 10:
        messages = messages[-10:]

    # Add user message
    messages.append({'role': 'user', 'content': user_message})

    # Get some recent news for context
    recent_news = News.objects.order_by('-parsed_at')[:20]

    # Get AI response
    ai_response = ai_get_chat_response(messages, recent_news)

    # Add AI response to history
    messages.append({'role': 'assistant', 'content': ai_response})
    
    # Save back to session
    request.session['ai_messages'] = messages

    return JsonResponse({
        'status': 'success',
        'ai_response': ai_response,
        'user_message': user_message,
        'timestamp': timezone.localtime().strftime("%H:%M")
    })

@csrf_exempt
def clear_ai_chat(request):
    if 'ai_messages' in request.session:
        del request.session['ai_messages']
    return JsonResponse({'status': 'success'})
