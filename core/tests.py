"""
Tests for the core application.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
User = get_user_model()


class IndexPage(TestCase):
    
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

    def test_index(self):
        self.assertEqual(self.response.status_code, 200)

   
class ProfileTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='vasya', password='testpassword')
    
    def test_index_response(self):
        profile = self.client.get("/profile")
        self.assertEqual(profile.status_code, 404) 
        self.client.force_login(self.user)
        profile_logged_in = self.client.get("/profile")
        self.assertEqual(profile_logged_in.status_code, 200)
