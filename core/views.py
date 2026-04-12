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
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import datetime
import json
import urllib.request
import re
from bs4 import BeautifulSoup
import hashlib
from .utils import ALL_TAGS, classify_news

def generate_deterministic_tags(url, title="", body="", seed_id=None):
    return classify_news(title, body, url=url, news_id=seed_id)

def get_top_tags(limit=5):
    from collections import Counter
    all_news = News.objects.all()
    counter = Counter()
    for n in all_news:
        counter.update(n.tags)
    
    top = counter.most_common(limit)
    return [tag for tag, count in top]

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

    top_tags = get_top_tags(5)
    return render(request, 'core/index.html', {
        'days_data': days_data,
        'top_tags': top_tags
    })


# ── Category → URL path prefixes on lenta.ru/YYYY/MM/DD/ ─────────────────────
# The date archive page (lenta.ru/YYYY/MM/DD/) has proper article HTML with
# reliable titles. We filter links by URL prefix to get category-specific ones.
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


# Per-request cache so we don't re-fetch the same date page for each category
_date_html_cache = {}

def _get_date_archive_html(date_obj):
    y, m, d = date_obj.year, date_obj.month, date_obj.day
    key = f'{y}-{m:02d}-{d:02d}'
    if key not in _date_html_cache:
        url = f'https://lenta.ru/{y}/{m:02d}/{d:02d}/'
        _date_html_cache[key] = _fetch_html(url)
    return _date_html_cache.get(key, '')


def _parse_lenta_category_day(category_label, keywords, date_obj):
    """
    Parse lenta.ru/YYYY/MM/DD/ and filter articles by keywords in title
    or by matching category path in URL.
    """
    y, m, d = date_obj.year, date_obj.month, date_obj.day
    html = _get_date_archive_html(date_obj)
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    section_paths = LENTA_SECTION_PATHS.get(category_label, [])
    date_seg = f'{y}/{m:02d}/{d:02d}/'

    articles = []
    seen = set()

    for a in soup.find_all('a', href=True):
        href = a['href']

        # Must contain the date segment
        if date_seg not in href:
            continue

        # Check if the URL path belongs to one of the category sections
        href_lower = href.lower()
        in_section_url = any(f'/{p}/' in href_lower for p in section_paths)

        full_url = 'https://lenta.ru' + href if href.startswith('/') else href
        if full_url in seen:
            continue

        # Extract title first to check keywords
        title_node = a.find(class_=re.compile(r'title'))
        raw = title_node.get_text(separator=' ') if title_node else a.get_text(separator=' ')
        title = re.sub(r'\s+', ' ', raw).strip()
        title = re.sub(r'\d{2}:\d{2}.*$', '', title).strip()

        # Filtering logic:
        # 1. Skip if title is obviously not a news headline
        if not title or len(title) < 20 or len(title.split()) < 3:
            continue

        seen.add(full_url)

        # Tag-based filtering: Check if the selected category is in the article's generated tags
        article_tags = generate_deterministic_tags(full_url, title=title)
        if category_label not in article_tags:
            continue

        seen.add(full_url)

        # Time extraction
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
            'tags': generate_deterministic_tags(full_url, title=title),
        })

        if len(articles) >= 20: # Slightly more per rubric
            break

    return articles


def _extract_article_body(url):
    """Fetch and extract readable text from an article URL."""
    html = _fetch_html(url)
    if not html:
        return ''
    soup = BeautifulSoup(html, 'lxml')
    blocks = []

    # Lenta-specific containers
    body_div = soup.find('div', class_=re.compile(r'topic-body__content|article-text|b-text|content__text'))
    if body_div:
        for p in body_div.find_all('p'):
            t = re.sub(r'\s+', ' ', p.get_text(separator=' ')).strip()
            if t:
                blocks.append(t)

    # Generic article fallback
    if not blocks:
        article = soup.find('article')
        if article:
            for p in article.find_all('p'):
                t = re.sub(r'\s+', ' ', p.get_text(separator=' ')).strip()
                if len(t) > 40:
                    blocks.append(t)

    # Last resort: all long paragraphs
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

    category_data = body.get('categoryData', []) # [{label, keywords}, ...]
    date_strs  = body.get('dates', [])

    results = {}

    for date_str in date_strs:
        try:
            date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue

        day_articles = []
        seen_urls = set()

        for cat_info in category_data:
            label = cat_info.get('label')
            keywords = cat_info.get('keywords', [])
            
            arts = _parse_lenta_category_day(label, keywords, date_obj)
            for art in arts:
                if art['url'] not in seen_urls:
                    seen_urls.add(art['url'])
                    day_articles.append(art)
                    if len(day_articles) >= 25:
                        break
            if len(day_articles) >= 25:
                break

        results[date_str] = day_articles

    return JsonResponse({'results': results})

