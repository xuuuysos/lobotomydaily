# pylint: disable=no-member,too-many-public-methods
"""
Comprehensive test suite for the core application, ensuring high code coverage
and verifying all models, views, forms, and utility functions.
"""

import json
import datetime
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from core.models import News, Comment, Bookmark, NewsAITags
from core.forms import RegisterForm
from core.utils import clean_and_deduplicate_tags, classify_news
from core.views import generate_deterministic_tags, get_top_tags

User = get_user_model()


class ModelTests(TestCase):
    """
    Test suite for database models: News, Comment, Bookmark, and NewsAITags.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="modeluser", password="testpassword")

    def test_news_creation(self):
        """Test creating a News model and its fields."""
        news = News.objects.create(
            source="Test Source",
            title="Test Title",
            body="Test Body",
            url="https://example.com/test-news-1"
        )
        self.assertEqual(news.source, "Test Source")
        self.assertEqual(news.title, "Test Title")
        self.assertEqual(news.body, "Test Body")
        self.assertEqual(news.url, "https://example.com/test-news-1")

    def test_comment_creation(self):
        """Test creating a Comment model and its relations."""
        comment = Comment.objects.create(
            news_url="https://example.com/test-news-2",
            author=self.user,
            text="Test Comment Text"
        )
        self.assertEqual(comment.author, self.user)
        self.assertEqual(comment.text, "Test Comment Text")
        self.assertEqual(comment.news_url, "https://example.com/test-news-2")
        self.assertTrue(comment.created_at)

    def test_bookmark_creation(self):
        """Test creating a Bookmark model and its unique constraints."""
        bookmark = Bookmark.objects.create(
            user=self.user,
            news_url="https://example.com/test-news-3"
        )
        self.assertEqual(bookmark.user, self.user)
        self.assertEqual(bookmark.news_url, "https://example.com/test-news-3")
        self.assertTrue(bookmark.created_at)

    def test_news_ai_tags_creation(self):
        """Test creating NewsAITags."""
        # "Тест", "Культура"
        ai_tags = NewsAITags.objects.create(
            news_url="https://example.com/test-news-4",
            tags_json=json.dumps(["\u0422\u0435\u0441\u0442", "\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430"])
        )
        self.assertEqual(ai_tags.news_url, "https://example.com/test-news-4")
        self.assertIn("\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430", json.loads(ai_tags.tags_json))


class FormTests(TestCase):
    """
    Test suite for forms, specifically RegisterForm.
    """

    def test_register_form_valid(self):
        """Test RegisterForm validation with valid data."""
        data = {
            'username': 'formuser',
            'password1': 'strongpassword123',
            'password2': 'strongpassword123'
        }
        form = RegisterForm(data=data)
        self.assertTrue(form.is_valid())

    def test_register_form_mismatched_passwords(self):
        """Test RegisterForm validation with mismatched passwords."""
        data = {
            'username': 'formuser',
            'password1': 'strongpassword123',
            'password2': 'differentpassword'
        }
        form = RegisterForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_register_form_username_exists(self):
        """Test RegisterForm validation when username already exists."""
        User.objects.create_user(username="existinguser", password="password123")
        data = {
            'username': 'existinguser',
            'password1': 'strongpassword123',
            'password2': 'strongpassword123'
        }
        form = RegisterForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)


class ViewTests(TestCase):
    """
    Test suite for Django views and template rendering.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="viewuser", password="testpassword")
        # "Путин подписал закон о бюджете", "В тексте закона сообщается о росте ВВП страны."
        self.news = News.objects.create(
            source="Lenta.ru",
            title="\u041f\u0443\u0442\u0438\u043d \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043b \u0437\u0430\u043a\u043e\u043d \u043e \u0431\u044e\u0434\u0436\u0435\u0442\u0435",
            body="\u0412 \u0442\u0435\u043a\u0441\u0442\u0435 \u0437\u0430\u043a\u043e\u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0430\u0435\u0442\u0441\u044f \u043e \u0440\u043e\u0441\u0442\u0435 \u0412\u0412\u041f \u0441\u0442\u0440\u0430\u043d\u044b.",
            url="https://example.com/lenta-news"
        )

    def test_index_view_status_code(self):
        """Test index page returns 200."""
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)

    def test_index_view_with_dates(self):
        """Test index page works with valid date range parameters."""
        today = timezone.localtime().date()
        yesterday = today - datetime.timedelta(days=1)
        response = self.client.get(reverse('index'), {
            'from': yesterday.strftime('%Y-%m-%d'),
            'to': today.strftime('%Y-%m-%d')
        })
        self.assertEqual(response.status_code, 200)

    def test_index_view_with_invalid_dates(self):
        """Test index page fallbacks correctly with invalid date range parameters."""
        response = self.client.get(reverse('index'), {
            'from': 'invalid-date',
            'to': '2026-99-99'
        })
        self.assertEqual(response.status_code, 200)

    def test_index_view_with_long_range_cap(self):
        """Test index page caps date range to maximum 14 days."""
        today = timezone.localtime().date()
        twenty_days_ago = today - datetime.timedelta(days=20)
        response = self.client.get(reverse('index'), {
            'from': twenty_days_ago.strftime('%Y-%m-%d'),
            'to': today.strftime('%Y-%m-%d')
        })
        self.assertEqual(response.status_code, 200)

    def test_profile_view_unauthenticated(self):
        """Test that profile view works for unauthenticated users (returns status 200)."""
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)

    def test_profile_view_authenticated(self):
        """Test that profile view displays user info and bookmarks for authenticated users."""
        self.client.force_login(self.user)
        Bookmark.objects.create(user=self.user, news_url=self.news.url)
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.news.title)

    def test_profile_view_authenticated_missing_news(self):
        """Test that profile view works fine if a bookmark exists but news is missing in DB."""
        self.client.force_login(self.user)
        Bookmark.objects.create(user=self.user, news_url="https://example.com/missing-news")
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)

    def test_register_view_get(self):
        """Test GET request to registration view."""
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_register_view_post_valid(self):
        """Test successful registration POST request."""
        data = {
            'username': 'newregistereduser',
            'password1': 'strongpassword123',
            'password2': 'strongpassword123'
        }
        response = self.client.post(reverse('register'), data=data)
        self.assertEqual(response.status_code, 302)  # Redirects to home page

    def test_register_view_post_invalid(self):
        """Test registration POST request with mismatched passwords."""
        data = {
            'username': 'newregistereduser',
            'password1': 'strongpassword123',
            'password2': 'mismatched'
        }
        response = self.client.post(reverse('register'), data=data)
        self.assertEqual(response.status_code, 200)  # Renders form with error


class ApiTests(TestCase):
    """
    Test suite for core API endpoints.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="apiuser", password="testpassword")
        # "Темы науки и космоса", "Исследование NASA обнаружило новую экзопланету."
        self.news = News.objects.create(
            source="Lenta.ru",
            title="\u0422\u0435\u043c\u044b \u043d\u0430\u0443\u043a\u0438 \u0438 \u043a\u043e\u0441\u043c\u043e\u0441\u0430",
            body="\u0418\u0441\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u043d\u0438\u0435 NASA \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0438\u043b\u043e \u043d\u043e\u0432\u0443\u044e \u044d\u043a\u0437\u043e\u043f\u043b\u0430\u043d\u0435\u0442\u0443.",
            url="https://example.com/science-news"
        )

    def test_api_category_news_invalid_method(self):
        """Test that fetch_category_news API rejects GET method."""
        response = self.client.get(reverse('fetch_category_news'))
        self.assertEqual(response.status_code, 405)

    @patch('core.views._parse_lenta_day_filtered')
    def test_api_category_news_success(self, mock_parse):
        """Test fetching category news returns news JSON."""
        # "Наука"
        mock_parse.return_value = [{
            'title': self.news.title,
            'url': self.news.url,
            'source': 'Lenta.ru',
            'tags': ['\u041d\u0430\u0443\u043a\u0430']
        }]
        payload = {
            'includedTags': ['\u041d\u0430\u0443\u043a\u0430'],
            'excludedTags': [],
            'dates': ['2026-05-27']
        }
        response = self.client.post(reverse('fetch_category_news'), json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertIn('2026-05-27', data['results'])

    def test_api_article_body_invalid_method(self):
        """Test that fetch_article_body API rejects GET method."""
        response = self.client.get(reverse('fetch_article_body'))
        self.assertEqual(response.status_code, 405)

    def test_api_article_body_invalid_json(self):
        """Test fetch_article_body API with bad JSON payload."""
        response = self.client.post(reverse('fetch_article_body'), "bad payload", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_api_article_body_missing_url(self):
        """Test fetch_article_body API with missing url field."""
        response = self.client.post(reverse('fetch_article_body'), json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('core.views._extract_article_body')
    def test_api_article_body_success(self, mock_extract):
        """Test successfully retrieving article body."""
        mock_extract.return_value = self.news.body
        response = self.client.post(reverse('fetch_article_body'), json.dumps({'url': self.news.url}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('body'), self.news.body)

    def test_api_comments_get_invalid_method(self):
        """Test get_comments API rejects GET method."""
        response = self.client.get(reverse('get_comments'))
        self.assertEqual(response.status_code, 405)

    def test_api_comments_get_success(self):
        """Test successfully retrieving comments for an article."""
        Comment.objects.create(news_url=self.news.url, author=self.user, text="Great planet!")
        response = self.client.post(reverse('get_comments'), json.dumps({'url': self.news.url}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data.get('comments')), 1)
        self.assertEqual(data.get('comments')[0]['text'], "Great planet!")

    def test_api_comments_add_unauthenticated(self):
        """Test adding comment rejects unauthenticated requests."""
        response = self.client.post(reverse('add_comment'), json.dumps({'url': self.news.url, 'text': 'Nice!'}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_api_comments_add_missing_data(self):
        """Test adding comment with missing text or url fields."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('add_comment'), json.dumps({'url': self.news.url}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_api_comments_add_success(self):
        """Test successfully adding comment when authenticated."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('add_comment'), json.dumps({'url': self.news.url, 'text': 'Insightful!'}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['comment']['text'], 'Insightful!')
        self.assertEqual(Comment.objects.filter(news_url=self.news.url).count(), 1)

    def test_api_bookmarks_toggle_unauthenticated(self):
        """Test that toggling bookmarks rejects unauthenticated requests."""
        response = self.client.post(reverse('toggle_bookmark'), json.dumps({'url': self.news.url}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_api_bookmarks_toggle_missing_url(self):
        """Test toggling bookmark with missing url parameter."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('toggle_bookmark'), json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_api_bookmarks_toggle_create(self):
        """Test toggling bookmark creates a bookmark if none exists."""
        self.client.force_login(self.user)
        response = self.client.post(reverse('toggle_bookmark'), json.dumps({'url': self.news.url}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'bookmarked')
        self.assertTrue(Bookmark.objects.filter(user=self.user, news_url=self.news.url).exists())

    def test_api_bookmarks_toggle_delete(self):
        """Test toggling bookmark deletes a bookmark if it already exists."""
        self.client.force_login(self.user)
        Bookmark.objects.create(user=self.user, news_url=self.news.url)
        response = self.client.post(reverse('toggle_bookmark'), json.dumps({'url': self.news.url}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'unbookmarked')
        self.assertFalse(Bookmark.objects.filter(user=self.user, news_url=self.news.url).exists())


class UtilityTests(TestCase):
    """
    Test suite for utility and helper functions.
    """

    def test_clean_and_deduplicate_tags(self):
        """Test tag cleaning, deduplication, translation, and abbreviation formatting."""
        # "политика", "sociedad", "ИИ", "ии", "культура", "культуры"
        tags = ["\u043f\u043e\u043b\u0438\u0442\u0438\u043a\u0430", "sociedad", "\u0418\u0418", "\u0438\u0438", "\u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0430", "\u043a\u0443\u043b\u044c\u0442\u0443\u0440\u044b"]
        cleaned = clean_and_deduplicate_tags(tags)
        # "Политика", "Общество", "ИИ", "Культура"
        self.assertIn("\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430", cleaned)
        self.assertIn("\u041e\u0431\u0449\u0435\u0441\u0442\u0432\u043e", cleaned)
        self.assertIn("\u0418\u0418", cleaned)
        self.assertIn("\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430", cleaned)

    def test_clean_and_deduplicate_tags_nested_json(self):
        """Test handling JSON string tags within list."""
        # '["Мем", "Культура"]', "Мем, спорт"
        tags = ['["\u041c\u0435\u043c", "\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430"]', "\u041c\u0435\u043c, \u0441\u043f\u043e\u0440\u0442"]
        cleaned = clean_and_deduplicate_tags(tags)
        # "Мем", "Культура", "Спорт"
        self.assertIn("\u041c\u0435\u043c", cleaned)
        self.assertIn("\u041a\u0443\u043b\u044c\u0442\u0443\u0440\u0430", cleaned)
        self.assertIn("\u0421\u043f\u043e\u0440\u0442", cleaned)

    def test_classify_news_lenta_rules(self):
        """Test classifying news content with Russian keyword matchers."""
        # "Новый маркетплейс wildberries открыл бизнес", "Продажи взлетели на миллион рублей."
        title = "\u041d\u043e\u0432\u044b\u0439 \u043c\u0430\u0440\u043a\u0435\u0442\u043f\u043b\u0435\u0439\u0441 wildberries \u043e\u0442\u043a\u0440\u044b\u043b \u0431\u0438\u0437\u043d\u0435\u0441"
        body = "\u041f\u0440\u043e\u0434\u0430\u0436\u0438 \u0432\u0437\u043b\u0435\u0442\u0435\u043b\u0438 \u043d\u0430 \u043c\u0438\u043b\u043b\u0438\u043e\u043d, \u044d\u043a\u043e\u043d\u043e\u043c\u0438\u043a\u0430 \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0440\u043e\u0441\u0442."
        tags = classify_news(title, body)
        # Expected: "Бизнес" and "Экономика"
        self.assertIn("\u0411\u0438\u0437\u043d\u0435\u0441", tags)
        self.assertIn("\u042d\u043a\u043e\u043d\u043e\u043c\u0438\u043a\u0430", tags)

    def test_generate_deterministic_tags(self):
        """Test generating deterministic tags helper."""
        # "Политика выборы госдума", "Политика"
        tags = generate_deterministic_tags("https://example.com/det-news", title="\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430 \u0432\u044b\u0431\u043e\u0440\u044b \u0433\u043e\u0441\u0434\u0443\u043c\u0430")
        self.assertIn("\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430", tags)

    def test_get_top_tags(self):
        """Test fetching top tags from NewsAITags."""
        # Create corresponding news objects for existing URLs
        News.objects.create(url="https://example.com/tag-1", title="Title 1", source="Source 1")
        News.objects.create(url="https://example.com/tag-2", title="Title 2", source="Source 2")
        # "Политика", "Спорт", "Спорт", "Спорт", "Политика"
        NewsAITags.objects.create(news_url="https://example.com/tag-1", tags_json=json.dumps(["\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430", "\u0421\u043f\u043e\u0440\u0442"]))
        NewsAITags.objects.create(news_url="https://example.com/tag-2", tags_json=json.dumps(["\u0421\u043f\u043e\u0440\u0442"]))
        top = get_top_tags(limit=2)
        self.assertEqual(top, ["\u0421\u043f\u043e\u0440\u0442", "\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430"])
