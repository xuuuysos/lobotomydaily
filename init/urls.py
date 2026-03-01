from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('profile', views.profile),
    path('accounts/', include("django.contrib.auth.urls")),
    path('register/', views.register, name='register'),
]
