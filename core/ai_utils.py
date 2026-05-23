"""
AI classification and news refinement utilities.
"""

import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("TOKEN")
BASE_URL = "https://openrouter.ai/api/v1"

# Circuit breaker to prevent page hang or scraper lag if OpenRouter has issues or rate limits
consecutive_ai_failures = 0
AI_CIRCUIT_BROKEN = False

client = None
if API_KEY:
    try:
        client = OpenAI(
            base_url=BASE_URL,
            api_key=API_KEY,
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Lobotomy Daily"
            },
            timeout=3.0,  # Fast 3.0 second timeout to immediately drop back to offline tags on API issues
            max_retries=0
        )
    except Exception as e:
        print(f"Failed to initialize OpenAI client: {e}")

def ai_classify_news(title, body, all_tags):
    """
    Uses AI to classify news into provided tags.
    """
    global consecutive_ai_failures, AI_CIRCUIT_BROKEN
    if AI_CIRCUIT_BROKEN or not client:
        return []

    prompt = f"""
    Ты — профессиональный редактор новостей.
    Проанализируй эту новостную статью и создай 3-5 широких, кратких тегов на русском языке.
    
    Заголовок статьи: {title}
    Текст статьи: {body[:500] if body else ""}

    Правила:
    1. Создай строго от 3 до 5 общих, широких категориальных тегов. Пиши их очень коротко (1-2 слова максимум).
    2. Ни в коем случае НЕ используй испанский, английский или другие языки. Все теги должны быть СТРОГО на русском языке.
    3. Не пиши слишком длинные или специфические фразы. Используй широкие понятия (например: "Политика", "Технологии", "МВД", "Космос", "Медицина", "Экономика", "Общество").
    4. Ответь СТРОГО в формате JSON с ключом "tags":
    {{
        "tags": ["Тег1", "Тег2", "Тег3"]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        
        # Try to extract JSON using regex in case model returns conversational text
        json_match = re.search(r'\{.*\}|\[.*\]', content, re.DOTALL)
        if json_match:
            clean_content = json_match.group(0)
        else:
            clean_content = re.sub(r'```json\n?|```', '', content).strip()
            
        data = json.loads(clean_content)
        
        # Look for tags in common field names
        possible_fields = ["tags", "categories", "keywords", "topics"]
        for field in possible_fields:
            if isinstance(data, dict) and field in data:
                return data[field]
        
        if isinstance(data, list):
            consecutive_ai_failures = 0
            return data
        consecutive_ai_failures = 0
        return []
    except Exception as e:
        print(f"AI Classification Error: {e}")
        consecutive_ai_failures += 1
        if consecutive_ai_failures >= 3:
            AI_CIRCUIT_BROKEN = True
            print("\n[AI Circuit Breaker] 3 consecutive failures. Disabling AI requests to prevent parsing lag!\n")
        return []


def ai_process_article(raw_title, raw_body):
    """
    Powerful AI processing: refines title, summarizes body, and generates dynamic tags.
    """
    global consecutive_ai_failures, AI_CIRCUIT_BROKEN
    if AI_CIRCUIT_BROKEN or not client:
        return raw_title, raw_body, []

    prompt = f"""
    Ты — шеф-редактор новостного портала 'Lobotomy Daily'.
    Обработай эту новостную статью для нашей премиальной ленты.
    
    Оригинальный заголовок: {raw_title}
    Оригинальный текст: {raw_body[:1500]}

    Задачи:
    1. Отредактируй заголовок: Сделай его профессиональным, завлекающим и строго на русском языке.
    2. Выжимка: Перепиши текст в виде лаконичной, читаемой выжимки (2-4 абзаца, строго на русском языке).
    3. Создай теги: Придумай от 3 до 5 общих, кратких тегов. Пиши их очень коротко (1-2 слова максимум) и только на русском языке (например: "Экономика", "Авто", "IT", "Общество", "Политика"). Избегай длинных, специфических фраз и иностранных языков (кроме общепринятых аббревиатур вроде IT).

    Верни СТРОГО JSON-объект следующей структуры:
    {{
        "title": "Отредактированный заголовок",
        "summary": "Текст выжимки",
        "tags": ["Тег1", "Тег2", "Тег3"]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        
        # Try to extract JSON using regex in case model returns conversational text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            clean_content = json_match.group(0)
        else:
            clean_content = re.sub(r'```json\n?|```', '', content).strip()
            
        data = json.loads(clean_content)
        
        consecutive_ai_failures = 0
        return (
            data.get("title", raw_title), 
            data.get("summary", data.get("text", data.get("body", raw_body))), 
            data.get("tags", data.get("categories", []))
        )
    except Exception as e:
        print(f"AI Processing Error: {e}")
        consecutive_ai_failures += 1
        if consecutive_ai_failures >= 3:
            AI_CIRCUIT_BROKEN = True
            print("\n[AI Circuit Breaker] 3 consecutive failures. Disabling AI requests to prevent parsing lag!\n")
        return raw_title, raw_body, []
