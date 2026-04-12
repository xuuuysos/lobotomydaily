from django.contrib import admin
from django.urls import path
import core.views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', core.views.index, name='index'),
    path('profile', core.views.profile),
    path('register/', core.views.register, name='register'),
    path('api/category-news/', core.views.fetch_category_news, name='fetch_category_news'),
    path('api/article-body/', core.views.fetch_article_body, name='fetch_article_body'),
]
