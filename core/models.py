from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class News(models.Model):
    id = models.BigAutoField(primary_key=True)
    source = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    body = models.TextField(null=True, blank=True)
    url = models.URLField(unique=True)
    parsed_at = models.DateTimeField(auto_now_add=True)

    @property
    def tags(self):
        from .utils import classify_news
        return classify_news(self.title, self.body, url=self.url, news_id=self.id)

    class Meta:
        managed = False
        db_table = 'news'

class Comment(models.Model):
    news_url = models.URLField(db_index=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
