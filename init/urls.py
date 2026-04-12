from django.contrib import admin
from django.urls import path, include
import core.views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/register/', core.views.register, name='register'),
    path('profile/', core.views.profile, name='profile'),
    path('', core.views.index, name='index'),
    path('api/category-news/', core.views.fetch_category_news, name='fetch_category_news'),
    path('api/article-body/', core.views.fetch_article_body, name='fetch_article_body'),
    path('api/comments/get/', core.views.get_comments, name='get_comments'),
    path('api/comments/add/', core.views.add_comment, name='add_comment'),
]
