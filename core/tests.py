# pylint: disable=no-member
"""
Tests for the core application.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import News

User = get_user_model()


class IndexPage(TestCase):
    """
    Test suite for the index page.
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
        """Test index page response and content."""
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lobotomy Daily")

    def test_profile_page_unauthenticated(self):
        """Test profile page access for unauthenticated users."""
        # Проверяем доступ неавторизованного пользователя к профилю
        # Обращаемся строго по URL-адресу с закрывающим слэшем
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)

    def test_index(self):
        """Test index response directly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


class ProfileTest(TestCase):
    """
    Test suite for profile-related pages.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='vasya', password='testpassword')

    def test_index_response(self):
        """Test profile URL redirect and authenticated access."""
        # Без слэша перенаправляет на URL со слэшем (301 redirect)
        profile_redirect = self.client.get("/profile")
        self.assertEqual(profile_redirect.status_code, 301)

        # Со слэшем возвращает 200
        profile = self.client.get("/profile/")
        self.assertEqual(profile.status_code, 200)

        # Авторизованный пользователь получает 200
        self.client.force_login(self.user)
        profile_logged_in = self.client.get("/profile/")
        self.assertEqual(profile_logged_in.status_code, 200)
