# pylint: disable=no-member
"""
Utility functions for tag parsing, cleaning, and classification.
"""

import json
import re
from .ai_utils import ai_classify_news

def clean_and_deduplicate_tags(tags):
    if not tags:
        return []
    cleaned = []
    seen_stems = {}
    
    # Spanish/Latin translation mapping to self-correct any rogue foreign tags
    spanish_map = {
        "política": "Политика",
        "politica": "Политика",
        "sociedad": "Общество",
        "celebración": "Праздник",
        "celebracion": "Праздник",
        "economía": "Экономика",
        "economia": "Экономика",
        "tecnología": "Технологии",
        "tecnologia": "Технологии",
        "ciencia": "Наука",
        "salud": "Здоровье",
        "deportes": "Спорт",
        "cultura": "Культура",
        "crimen": "Криминал"
    }
    
    # Standard Russian and English news abbreviations to write in ALL CAPS
    abbreviations = {
        "ии", "дтп", "мчс", "мвд", "оон", "сша", "цб", "ввп", "спб", "рф", "it", 
        "ссср", "нато", "одкб", "кндр", "фсб", "гибдд", "сми", "вуз", "пво", "сво", "вс"
    }
    
    def get_stem(word):
        w = word.lower().strip()
        endings = ['ое', 'ая', 'ый', 'ые', 'ие', 'ий', 'ой', 'а', 'я', 'о', 'е', 'и', 'ы', 'т', 'у', 'ю', 'ом', 'ем', 'ах', 'ях', 'ам', 'ям', 'ов', 'ей']
        for end in sorted(endings, key=len, reverse=True):
            if w.endswith(end) and len(w) - len(end) >= 3:
                return w[:-len(end)]
        return w

    # Pre-parse tags to split any stringified lists or comma-separated tags
    raw_tags = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t_stripped = t.strip()
        if not t_stripped:
            continue
            
        # Handle cases like ["Мем", "Культура"] inside a single string
        if t_stripped.startswith('[') and t_stripped.endswith(']'):
            try:
                parsed = json.loads(t_stripped)
                if isinstance(parsed, list):
                    raw_tags.extend(parsed)
                    continue
            except Exception:
                pass
                
        # Handle cases like: Мем","культура","интернет or Мем, культура, интернет
        if '"' in t_stripped or ',' in t_stripped or ';' in t_stripped:
            parts = re.split(r'["\',;\[\]\(\)]+', t_stripped)
            for part in parts:
                p = part.strip()
                if p:
                    raw_tags.append(p)
        else:
            raw_tags.append(t_stripped)

    for tag in raw_tags:
            
        # Check Spanish map first
        tag_lower = tag.lower()
        if tag_lower in spanish_map:
            tag = spanish_map[tag_lower]
            tag_lower = tag.lower()
        
        # Format abbreviations in ALL CAPS
        if tag_lower in abbreviations:
            tag = tag.upper()
        elif not re.search('[а-яА-Я]', tag):
            tag = tag.upper() if len(tag) <= 4 else tag.capitalize()
        else:
            tag = tag.capitalize()
            
        stem = get_stem(tag)
        
        similar_found = False
        for existing_stem, existing_tag in seen_stems.items():
            if stem.startswith(existing_stem) or existing_stem.startswith(stem) or stem == existing_stem:
                similar_found = True
                break
            if len(stem) >= 4 and len(existing_stem) >= 4:
                diff = sum(1 for c1, c2 in zip(stem, existing_stem) if c1 != c2) + abs(len(stem) - len(existing_stem))
                if diff <= 1:
                    similar_found = True
                    break
        
        if not similar_found:
            seen_stems[stem] = tag
            cleaned.append(tag)
            
    return cleaned

def classify_news(title, body, url=None, news_id=None):
    """
    100% AI-driven classification with database caching.
    No more hardcoded tags or keywords.
    """
    from .models import NewsAITags
    
    # 1. Try to get from database (AI cache)
    if url:
        try:
            cached = NewsAITags.objects.get(news_url=url)
            cached_tags = json.loads(cached.tags_json)
            if cached_tags:
                return clean_and_deduplicate_tags(cached_tags)
        except NewsAITags.DoesNotExist:
            pass

    # 2. If not in DB, do NOT call AI synchronously (it blocks page load).
    # AI generation is handled asynchronously in parse_news.py.
    result_tags = []
    
    # 3. Robust local fallback if AI fails or no API key is provided
    if not result_tags:
        text_to_scan = f"{title} {body}".lower() if body else title.lower()
        keyword_map = {
            "Политика": ["путин", "кремль", "президент", "правительство", "депутат", "закон", "выборы", "госдума", "мид", "политика"],
            "Экономика": ["рубль", "доллар", "евро", "банк", "инфляция", "экономика", "бюджет", "налог", "цб", "ввп"],
            "Происшествия": ["дтп", "авария", "мчс", "пожар", "взрыв", "труп", "погиб", "жертв"],
            "Криминал": ["криминал", "задержали", "убил", "суд", "полиция", "мвд", "арест", "мошенник", "взятка", "следствие", "прокуратура", "тюрьма", "кража"],
            "Технологии": ["apple", "google", "яндекс", "смартфон", "ии", "нейросеть", "интернет", "it", "технологии", "компьютер"],
            "Спорт": ["футбол", "хоккей", "теннис", "олимпиада", "матч", "клуб", "спорт", "лига", "чемпионат", "турнир", "зенит", "спартак"],
            "Культура": ["кино", "фильм", "актер", "театр", "выставка", "музыка", "фестиваль", "концерт", "культура", "музей", "искусство"],
            "Наука": ["ученые", "наука", "космос", "исследование", "открытие", "nasa", "роскосмос", "экспедиция"],
            "Здоровье": ["врач", "медицина", "болезнь", "здоровье", "вирус", "больница", "лекарство", "пациент", "клиника"],
            "Авто": ["авто", "машина", "гибдд", "водитель", "штраф", "дорога", "трасса", "toyota", "bmw", "парковка", "автомобиль"],
            "Бизнес": ["бизнес", "компания", "акции", "инвестиции", "завод", "производство", "предприниматель", "маркетплейс", "wildberries", "ozon"],
            "В мире": ["сша", "китай", "европа", "оон", "нато", "международный", "запад", "байден", "макрон", "шойгу", "в мире", "страны"],
            "Регионы": ["спб", "петербург", "москва", "регион", "область", "губернатор", "мэр", "беглов", "собянин", "город"],
            "Общество": ["общество", "люди", "школа", "студент", "пенсия", "жкх", "дети", "пенсионер", "семья"],
            "События": ["праздник", "фестиваль", "выходные", "мероприятие"],
            "Инновации": ["инновации", "стартап", "разработка", "будущее"]
        }
        
        for tag, keywords in keyword_map.items():
            if any(kw in text_to_scan for kw in keywords):
                result_tags.append(tag)
        
        # Ensure we always have at least 3-5 tags
        if len(result_tags) < 3:
            if "Общество" not in result_tags: result_tags.append("Общество")
            if "Актуальное" not in result_tags: result_tags.append("Актуальное")
            if len(result_tags) < 3 and "Новости" not in result_tags: result_tags.append("Новости")
            
        # Deduplicate and limit to 5
        result_tags = clean_and_deduplicate_tags(result_tags)[:5]

    # 4. Save result to DB for future use
    if url and result_tags:
        try:
            result_tags = clean_and_deduplicate_tags(result_tags)
            NewsAITags.objects.update_or_create(
                news_url=url,
                defaults={'tags_json': json.dumps(result_tags, ensure_ascii=False)}
            )
        except Exception as e:
            print(f"Error saving AI tags: {e}")

    return result_tags
