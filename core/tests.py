from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
import json
import datetime

from .models import News, NewsAITags, Comment
from .utils import clean_and_deduplicate_tags, classify_news

User = get_user_model()


class UtilityTests(TestCase):
    """
    Тестирование вспомогательных функций форматирования и очистки тегов.
    """

    def test_clean_and_deduplicate_tags(self):
        # 1. Тест перевода тегов (испанский/латинский -> русский)
        raw_spanish = ["política", "ciencia", "deportes"]
        cleaned_spanish = clean_and_deduplicate_tags(raw_spanish)
        self.assertEqual(cleaned_spanish, ["Политика", "Наука", "Спорт"])

        # 2. Тест приведения аббревиатур к верхнему регистру
        raw_abbr = ["ии", "сша", "дтп"]
        cleaned_abbr = clean_and_deduplicate_tags(raw_abbr)
        self.assertEqual(cleaned_abbr, ["ИИ", ["США"][0], "ДТП"])

        # 3. Тест удаления однокоренных дубликатов (стемминг)
        raw_stems = ["Технология", "технологии", "технологический"]
        cleaned_stems = clean_and_deduplicate_tags(raw_stems)
        self.assertEqual(len(cleaned_stems), 1)
        self.assertEqual(cleaned_stems[0], "Технология")

        # 4. Тест удаления нечетких дубликатов (расстояние Левенштейна)
        raw_fuzzy = ["Политика", "Политико"]
        cleaned_fuzzy = clean_and_deduplicate_tags(raw_fuzzy)
        self.assertEqual(len(cleaned_fuzzy), 1)

        # 5. Тест парсинга строковых списков
        raw_string_list = ['["Культура", "Кино"]']
        cleaned_string_list = clean_and_deduplicate_tags(raw_string_list)
        self.assertEqual(cleaned_string_list, ["Культура", "Кино"])


class ModelAndClassificationTests(TestCase):
    """
    Тестирование моделей и локальной оффлайн-классификации новостей.
    """

    def setUp(self):
        self.news_url = "https://example.com/test-news-1"
        self.news = News.objects.create(
            source="Test Source",
            title="Биткоин взлетел на фоне новостей от ЦБ",
            body="Криптовалютный рынок демонстрирует рост. Центральный Банк (ЦБ) опубликовал отчет.",
            url=self.news_url
        )

    def test_news_creation(self):
        self.assertEqual(self.news.source, "Test Source")
        self.assertEqual(self.news.url, self.news_url)

    def test_local_offline_classification(self):
        # Проверяем, что оффлайн-классификатор правильно подбирает тег "Экономика" по ключевым словам ("ЦБ", "Биткоин")
        tags = self.news.tags
        self.assertIn("Экономика", tags)
        self.assertTrue(len(tags) >= 3)  # Всегда дополняет до 3 тегов

    def test_classification_db_caching(self):
        # Проверяем, что результаты классификации сохраняются в кэш NewsAITags
        _ = self.news.tags
        cached = NewsAITags.objects.filter(news_url=self.news_url).exists()
        self.assertTrue(cached)

        # Проверяем, что при повторном запросе теги берутся из кэша
        cached_obj = NewsAITags.objects.get(news_url=self.news_url)
        cached_obj.tags_json = json.dumps(["Первыйкастомныйтег", "Второйтег"], ensure_ascii=False)
        cached_obj.save()

        # Повторный вызов должен вернуть теги из кэша
        self.assertEqual(self.news.tags, ["Первыйкастомныйтег", "Второйтег"])


class ViewAndAPITests(TestCase):
    """
    Тестирование представлений (views) и API эндпоинтов.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        self.news_url = "https://example.com/api-test-news"
        self.news = News.objects.create(
            source="Lenta.ru",
            title="В Санкт-Петербурге открылась художественная выставка",
            body="В Эрмитаже представили новые картины мировых авторов.",
            url=self.news_url
        )

    def test_index_page(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lobotomy Daily")

    def test_profile_page_unauthenticated(self):
        # Проверяем доступ неавторизованного пользователя к профилю
        # Обращаемся строго по URL-адресу с закрывающим слэшем
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)

    def test_profile_page_authenticated(self):
        # Проверяем авторизованного пользователя
        self.client.force_login(self.user)
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testuser")

    def test_api_article_body_invalid(self):
        # Должен возвращать ошибку при GET запросе
        response = self.client.get(reverse("fetch_article_body"))
        self.assertEqual(response.status_code, 405)

    def test_api_article_body_valid(self):
        # Проверяем POST-запрос получения тела статьи
        response = self.client.post(
            reverse("fetch_article_body"),
            data=json.dumps({"url": self.news_url}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("body", data)

    def test_comments_flow(self):
        # 1. Получение списка комментариев (пока пустой)
        response_get = self.client.post(
            reverse("get_comments"),
            data=json.dumps({"url": self.news_url}),
            content_type="application/json"
        )
        self.assertEqual(response_get.status_code, 200)
        data_get = json.loads(response_get.content)
        self.assertEqual(data_get["comments"], [])

        # 2. Попытка добавления комментария без авторизации (должно быть 403 Forbidden)
        response_add_unauth = self.client.post(
            reverse("add_comment"),
            data=json.dumps({"url": self.news_url, "text": "Тестовый комментарий"}),
            content_type="application/json"
        )
        self.assertEqual(response_add_unauth.status_code, 403)

        # 3. Авторизация и добавление комментария
        self.client.force_login(self.user)
        response_add_auth = self.client.post(
            reverse("add_comment"),
            data=json.dumps({"url": self.news_url, "text": "Великолепная статья!"}),
            content_type="application/json"
        )
        self.assertEqual(response_add_auth.status_code, 200)

        # 4. Проверка, что комментарий теперь отдается через GET API
        response_get_again = self.client.post(
            reverse("get_comments"),
            data=json.dumps({"url": self.news_url}),
            content_type="application/json"
        )
        data_get_again = json.loads(response_get_again.content)
        self.assertEqual(len(data_get_again["comments"]), 1)
        self.assertEqual(data_get_again["comments"][0]["author"], "testuser")
        self.assertEqual(data_get_again["comments"][0]["text"], "Великолепная статья!")


class AIChatTests(TestCase):
    """
    Тестирование API ИИ-ассистента и очистки истории.
    """

    def setUp(self):
        self.client = Client()

    def test_ai_chat_empty_message(self):
        response = self.client.post(
            reverse("send_ai_message"),
            data=json.dumps({"message": ""}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_ai_chat_clear(self):
        response = self.client.post(reverse("clear_ai_chat"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "success")
