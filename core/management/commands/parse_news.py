import os
import sys
import datetime
import urllib.request
import re
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import News

class Command(BaseCommand):
    help = 'Parses news from Lenta.ru and Fontanka.ru and saves them to the database.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Number of days to parse')
        parser.add_argument('--clear', action='store_true', help='Clear database before parsing')
        parser.add_argument('--limit', type=int, default=15, help='Limit of news items per day')

    def handle(self, *args, **options):
        days = options['days']
        clear = options['clear']
        limit = options['limit']

        if clear:
            self.stdout.write(self.style.WARNING('Clearing existing news...'))
            News.objects.all().delete()

        now = timezone.localtime()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        created_total = 0
        ru_months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 
            'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }

        for day_offset in range(days):
            target_date = start_of_today - datetime.timedelta(days=day_offset)
            self.stdout.write(f"Fetching news for {target_date.strftime('%Y-%m-%d')}...")

            lenta = self.get_lenta_links(target_date, ru_months)
            fontanka = self.get_fontanka_links(target_date)

            day_links = []
            max_len = max(len(lenta), len(fontanka))
            for i in range(max_len):
                if i < len(fontanka): day_links.append(fontanka[i])
                if i < len(lenta): day_links.append(lenta[i])

            unique_links = []
            seen = set()
            for d in day_links:
                if d['url'] not in seen:
                    seen.add(d['url'])
                    unique_links.append(d)

            # Select up to limit
            selected = unique_links[:limit]
            
            day_count = 0
            for item in selected:
                try:
                    # Check if already exists to skip extraction if not needed (optional but faster)
                    # For now, let's just use update_or_create
                    
                    body = self.extract_text_from_url(item['url'])
                    
                    news_item, created = News.objects.update_or_create(
                        url=item['url'],
                        defaults={
                            'source': item['source'],
                            'title': item['title'],
                            'body': body,
                            'parsed_at': item['pub_time']
                        }
                    )
                    
                    if created:
                        day_count += 1
                        created_total += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to save {item['url']}: {e}"))

            self.stdout.write(self.style.SUCCESS(f"  Added {day_count} new items for {target_date.strftime('%Y-%m-%d')}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully processed news. Total new items: {created_total}"))

    def fetch_html(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception:
            return ""

    def extract_text_from_url(self, url):
        html = self.fetch_html(url)
        if not html: return "Текст недоступен."
        soup = BeautifulSoup(html, 'lxml')
        
        text_blocks = []
        # Lenta/Fontanka common logic
        body_div = soup.find('div', class_=re.compile(r'topic-body__content|article-text|b-text|content__text'))
        if not body_div:
            body_div = soup.find('article')
            
        if body_div:
            for p in body_div.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 40:
                    text_blocks.append(text)
        
        if not text_blocks:
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 100:
                    text_blocks.append(text)

        full_text = "\n\n".join(text_blocks[:8])
        return full_text or "Текст статьи недоступен. Пожалуйста, посетите сайт источника."

    def get_lenta_links(self, date_obj, ru_months):
        url = f"https://lenta.ru/{date_obj.year}/{date_obj.month:02d}/{date_obj.day:02d}/"
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, 'lxml')
        links = []
        date_pattern = f"/news/{date_obj.year}/{date_obj.month:02d}/{date_obj.day:02d}/"
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(date_pattern):
                full_url = "https://lenta.ru" + href
                
                title_node = a.find(class_=re.compile(r'title'))
                raw_title = title_node.get_text(separator=' ') if title_node else a.get_text(separator=' ')
                title = re.sub(r'\s+', ' ', raw_title).strip()
                title = re.sub(r'\d{2}:\d{2}.*$', '', title).strip()
                
                pub_time = timezone.make_aware(datetime.datetime(date_obj.year, date_obj.month, date_obj.day, 8, 0))
                time_node = a.find('time') or a.find(class_=re.compile(r'date'))
                if time_node:
                    t_str = time_node.get_text(strip=True)
                    m_full = re.search(r'(\d{2}):(\d{2}),\s*(\d{1,2})\s+([а-яА-Я]+)\s+(\d{4})', t_str)
                    if m_full:
                        h, mn, d, mon_str, y = m_full.groups()
                        mon_num = ru_months.get(mon_str.lower(), date_obj.month)
                        pub_time = timezone.make_aware(datetime.datetime(int(y), mon_num, int(d), int(h), int(mn)))
                    else:
                        m = re.search(r'(\d{2}):(\d{2})', t_str)
                        if m:
                            pub_time = timezone.make_aware(datetime.datetime(date_obj.year, date_obj.month, date_obj.day, int(m.group(1)), int(m.group(2))))
                
                if title and len(title) > 20:
                    links.append({'url': full_url, 'title': title, 'source': 'Lenta.ru', 'pub_time': pub_time})
        return links

    def get_fontanka_links(self, date_obj):
        url = f"https://www.fontanka.ru/{date_obj.year}/{date_obj.month:02d}/{date_obj.day:02d}/all.html"
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, 'lxml')
        links = []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            m_url = re.search(r'^/(\d{4})/(\d{2})/(\d{2})/', href)
            if m_url and href.endswith("/"):
                y, mon, d = map(int, m_url.groups())
                if y != date_obj.year or mon != date_obj.month or d != date_obj.day:
                    continue
                
                full_url = "https://www.fontanka.ru" + href
                title = a.get_text(strip=True)
                
                pub_time = timezone.make_aware(datetime.datetime(y, mon, d, 12, 0))
                parent = a.find_parent(['div', 'li', 'article'])
                time_node = parent.find('time') if parent else None
                if not time_node:
                    time_node = a.find_previous('time')
                
                if time_node:
                    m = re.search(r'(\d{2}):(\d{2})', time_node.get_text(strip=True))
                    if m:
                        pub_time = timezone.make_aware(datetime.datetime(y, mon, d, int(m.group(1)), int(m.group(2))))
                
                if title and len(title) > 20:
                    links.append({'url': full_url, 'title': title, 'source': 'Fontanka.ru', 'pub_time': pub_time})
        return links
