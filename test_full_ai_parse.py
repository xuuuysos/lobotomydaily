import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'init.settings')
django.setup()

from core.ai_utils import ai_process_article

title = "Фонтанка: В Петербурге задержали мужчину с гранатой"
body = "Сотрудники полиции задержали жителя Калининского района, который размахивал предметом, похожим на гранату. Позже выяснилось, что это муляж."

print("--- Calling AI Process News Item ---")
new_title, new_summary, tags = ai_process_article(title, body)

print(f"Original Title: {title}")
print(f"Refined Title: {new_title}")
print(f"AI Summary: {new_summary}")
print(f"AI Tags: {tags}")
