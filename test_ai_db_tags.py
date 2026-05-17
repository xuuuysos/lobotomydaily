import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'init.settings')
django.setup()

from core.utils import classify_news
from core.models import NewsAITags

test_title = "Новое достижение в квантовых вычислениях от Google"
test_url = "https://example.com/quantum-google-news-123"

print("--- Testing Smart AI Tags ---")

# First call should call AI (if key present) and save to DB
print("1. Calling classify_news for the first time...")
tags1 = classify_news(test_title, "Ученые из Google представили новый квантовый процессор.", url=test_url)
print(f"Resulting tags: {tags1}")

# Check if saved to DB
exists = NewsAITags.objects.filter(news_url=test_url).exists()
print(f"Saved to database: {exists}")

if exists:
    cached_obj = NewsAITags.objects.get(news_url=test_url)
    print(f"Database content: {cached_obj.tags_json}")

# Second call should be instant (from DB)
print("\n2. Calling classify_news again (should be from cache)...")
tags2 = classify_news(test_title, "Another body text", url=test_url)
print(f"Resulting tags: {tags2}")

if tags1 == tags2:
    print("\nSUCCESS: AI tags are persistent and under AI influence!")
else:
    print("\nWARNING: Result difference detected.")
