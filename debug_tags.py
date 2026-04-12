from core.utils import classify_news, TAG_KEYWORDS

def classify_debug(title, body):
    text = (title + " " + (body or "")).lower()
    matches = {}
    for tag, keywords in TAG_KEYWORDS.items():
        reasons = []
        if tag.lower() in text:
            reasons.append(f"tag_match:{tag}")
        for kw in keywords:
            import re
            if len(kw) < 4:
                if re.search(r'\b' + re.escape(kw) + r'\b', text):
                    reasons.append(f"kw_match:{kw}")
            else:
                if kw in text:
                    reasons.append(f"kw_match:{kw}")
        if reasons:
            matches[tag] = reasons
    return matches

test_titles = [
    "«Это выбор между Европой и Россией». Почему победа проукраинских сил в Венгрии проблема для Зеленского",
]

for title in test_titles:
    res = classify_debug(title, "")
    print(f"Title: {title}")
    for tag, reasons in res.items():
        print(f"  [{tag}]: {', '.join(reasons)}")
    print("-" * 50)
