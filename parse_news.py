import os
import sys
import django
from django.utils import timezone
import datetime
import urllib.request
from bs4 import BeautifulSoup
import re

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'init.settings')
django.setup()

from core.models import News

def fetch_html(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        response = urllib.request.urlopen(req, timeout=10)
        return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def extract_text_from_url(url):
    html = fetch_html(url)
    if not html:
        return "Текст недоступен."
    soup = BeautifulSoup(html, 'lxml')
    
    # Common text containers
    text_blocks = []
    
    # For Lenta
    lenta_body = soup.find('div', class_=re.compile(r'topic-body__content|b-text'))
    if lenta_body:
        for p in lenta_body.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                text_blocks.append(text)
                
    # For Fontanka
    fontanka_body = soup.find('article', class_=re.compile(r'article')) or soup.find(id=re.compile('article'))
    if fontanka_body:
        for p in fontanka_body.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                text_blocks.append(text)

    # General fallback
    if not text_blocks:
        article = soup.find('article')
        if article:
            for p in article.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 40:
                    text_blocks.append(text)
    
    if not text_blocks:
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 100:
                text_blocks.append(text)

    full_text = "\n\n".join(text_blocks[:6])
    if not full_text.strip():
        return "Текст статьи недоступен. Нажмите кнопку ниже, чтобы прочитать оригинал на сайте."
    return full_text

ru_months = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12, 'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'июн': 6, 'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12}

def get_lenta_links(date_obj):
    url = f"https://lenta.ru/{date_obj.year}/{date_obj.month:02d}/{date_obj.day:02d}/"
    html = fetch_html(url)
    soup = BeautifulSoup(html, 'lxml')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith(f"/news/{date_obj.year}/{date_obj.month:02d}/{date_obj.day:02d}/"):
            full_url = "https://lenta.ru" + href
            
            title_node = a.find(class_=re.compile(r'title'))
            title = title_node.get_text(strip=True) if title_node else a.get_text(strip=True)
            title = re.sub(r'\d{2}:\d{2}.*$', '', title).strip() # extra safety
            
            pub_time = date_obj.replace(hour=8, minute=0)
            time_node = a.find('time') or a.find(class_=re.compile(r'date'))
            if time_node:
                t_str = time_node.get_text(strip=True)
                m_full = re.search(r'(\d{2}):(\d{2}),\s*(\d{1,2})\s+([а-яА-Яa-zA-Z]+)\s+(\d{4})', t_str)
                if m_full:
                    h, mn, d, mon_str, y = m_full.groups()
                    mon_num = ru_months.get(mon_str.lower(), date_obj.month)
                    pub_time = timezone.make_aware(datetime.datetime(int(y), mon_num, int(d), int(h), int(mn)))
                else:
                    m = re.search(r'(\d{2}):(\d{2})', t_str)
                    if m:
                        pub_time = date_obj.replace(hour=int(m.group(1)), minute=int(m.group(2)))
            
            if title and full_url not in [x['url'] for x in links]:
                links.append({'url': full_url, 'title': title, 'source': 'Lenta.ru', 'pub_time': pub_time})
    return links

def get_fontanka_links(date_obj):
    url = f"https://www.fontanka.ru/{date_obj.year}/{date_obj.month:02d}/{date_obj.day:02d}/all.html"
    html = fetch_html(url)
    soup = BeautifulSoup(html, 'lxml')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        m_url = re.search(r'^/(\d{4})/(\d{2})/(\d{2})/', href)
        if m_url and href.endswith("/"):
            y, mon, d = m_url.groups()
            y, mon, d = int(y), int(mon), int(d)
            if y != date_obj.year or mon != date_obj.month or d != date_obj.day:
                continue
            
            pub_time = None
            time_node = getattr(a.find_parent(['div', 'li', 'article']), 'find', lambda x: None)('time') or a.find_previous('time')
            
            if time_node:
                 m = re.search(r'(\d{2}):(\d{2})', time_node.get_text(strip=True))
                 if m:
                     pub_time = timezone.make_aware(datetime.datetime(y, mon, d, int(m.group(1)), int(m.group(2))))
            
            if pub_time is None:
                continue
                         
            if title and len(title) > 20 and full_url not in [x['url'] for x in links]:
                links.append({'url': full_url, 'title': title, 'source': 'Fontanka.ru', 'pub_time': pub_time})
    return links

def main():
    News.objects.all().delete()
    
    now = timezone.localtime()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    created_count = 0
    
    for day_offset in range(7):
        target_obj = start_of_today - datetime.timedelta(days=day_offset)
        print(f"Fetching news for {target_obj.strftime('%Y-%m-%d')}...")
        
        lenta = get_lenta_links(target_obj)
        fontanka = get_fontanka_links(target_obj)
        
        day_links = []
        for i in range(max(len(lenta), len(fontanka))):
            if i < len(fontanka):
                day_links.append(fontanka[i])
            if i < len(lenta):
                day_links.append(lenta[i])
                
        unique_links = []
        seen = set()
        for d in day_links:
            if d['url'] not in seen:
                seen.add(d['url'])
                unique_links.append(d)
                
        selected = unique_links[:5]
        
        for idx, item in enumerate(selected):
            print(f"  -> extracting text for {item['url']}")
            body = extract_text_from_url(item['url'])
            
            pub_time = item['pub_time']
            
            try:
                n = News.objects.create(
                    source=item['source'],
                    title=item['title'],
                    body=body,
                    url=item['url']
                )
                News.objects.filter(id=n.id).update(parsed_at=pub_time)
                created_count += 1
            except Exception as e:
                print(f"Failed to save {item['url']}: {e}")

    print(f"Successfully populated {created_count} news items with actual text and dates.")

if __name__ == '__main__':
    main()
