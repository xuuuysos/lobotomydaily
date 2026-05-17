import os
import sys
import datetime
import urllib.request
import re
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import News, NewsAITags
from core.ai_utils import ai_process_article
import json

class Command(BaseCommand):
    help = 'Parses news from Lenta.ru and Fontanka.ru and saves them to the database.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Number of days to parse')
        parser.add_argument('--clear', action='store_true', help='Clear database before parsing')
        parser.add_argument('--limit', type=int, default=5, help='Limit of news items per day')
        parser.add_argument('--date', type=str, help='Start date for parsing (YYYY-MM-DD)')

    def handle(self, *args, **options):
        days = options['days']
        clear = options['clear']
        limit = options['limit']

        if clear:
            self.stdout.write(self.style.WARNING('Clearing existing news and cached tags...'))
            News.objects.all().delete()
            NewsAITags.objects.all().delete()

        now = timezone.localtime()
        if options['date']:
            try:
                dt = datetime.datetime.strptime(options['date'], '%Y-%m-%d')
                start_point = timezone.make_aware(dt.replace(hour=0, minute=0, second=0, microsecond=0))
            except ValueError:
                self.stdout.write(self.style.ERROR(f"Invalid date format: {options['date']}. Use YYYY-MM-DD"))
                return
        else:
            start_point = now.replace(hour=0, minute=0, second=0, microsecond=0)

        created_total = 0
        ru_months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6, 
            'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }

        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 1. Fetch links for all days in parallel!
        all_selected_links = []
        
        def fetch_links_for_day(day_offset):
            target_date = start_point - datetime.timedelta(days=day_offset)
            lenta = self.get_lenta_links(target_date, ru_months)
            fontanka = self.get_fontanka_links(target_date)
            ria = self.get_ria_links(target_date)
            
            day_links = []
            max_len = max(len(lenta), len(fontanka), len(ria))
            for i in range(max_len):
                if i < len(ria): day_links.append(ria[i])
                if i < len(fontanka): day_links.append(fontanka[i])
                if i < len(lenta): day_links.append(lenta[i])

            unique_links = []
            seen = set()
            for d in day_links:
                if d['url'] not in seen:
                    seen.add(d['url'])
                    unique_links.append(d)
            
            return target_date, unique_links[:limit]

        self.stdout.write("Fetching all daily index pages in parallel...")
        day_results = {}
        with ThreadPoolExecutor(max_workers=max(1, days)) as executor:
            futures = {executor.submit(fetch_links_for_day, i): i for i in range(days)}
            for future in as_completed(futures):
                target_date, selected = future.result()
                day_results[target_date] = selected
                all_selected_links.extend(selected)

        # 2. Process all articles across all days in parallel!
        self.stdout.write(f"Processing all {len(all_selected_links)} articles in parallel...")
        
        def process_single_item(item):
            body = self.extract_text_from_url(item['url'])
            self.stdout.write(f"  AI is processing: {item['title'][:50]}...")
            refined_title, refined_body, ai_tags = ai_process_article(item['title'], body)
            return item, refined_title, refined_body, ai_tags

        processed_results = []
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(process_single_item, item): item for item in all_selected_links}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    processed_results.append(res)
                except Exception as e:
                    item = futures[future]
                    self.stdout.write(self.style.ERROR(f"Failed processing network/AI for {item['url']}: {e}"))

        # 3. Save sequentially in the main thread to avoid SQLite locks
        self.stdout.write("Saving all parsed news to the database...")
        for item, refined_title, refined_body, ai_tags in processed_results:
            try:
                news_item, created = News.objects.update_or_create(
                    url=item['url'],
                    defaults={
                        'source': item['source'],
                        'title': refined_title,
                        'body': refined_body,
                        'parsed_at': item['pub_time']
                    }
                )

                # Save AI tags immediately to our new table
                if ai_tags:
                    NewsAITags.objects.update_or_create(
                        news_url=item['url'],
                        defaults={'tags_json': json.dumps(ai_tags, ensure_ascii=False)}
                    )
                
                if created:
                    created_total += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to save {item['url']}: {e}"))

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
        # Lenta/Fontanka/RIA common logic
        body_div = soup.find('div', class_=re.compile(r'topic-body__content|article-text|b-text|content__text|article__body|article__text'))
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

    def get_ria_links(self, date_obj):
        url = f"https://ria.ru/{date_obj.year}{date_obj.month:02d}{date_obj.day:02d}/"
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, 'lxml')
        links = []
        date_pattern = f"https://ria.ru/{date_obj.year}{date_obj.month:02d}{date_obj.day:02d}/"
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(date_pattern) and href.endswith(".html"):
                title = a.get_text(strip=True)
                if not title:
                    title = a.get('title', '')
                
                pub_time = timezone.make_aware(datetime.datetime(date_obj.year, date_obj.month, date_obj.day, 12, 0))
                if title and len(title) > 20:
                    links.append({'url': href, 'title': title, 'source': 'RIA.ru', 'pub_time': pub_time})
        return links
