from django.db import models

# Create your models here.

class News(models.Model):
    id = models.BigAutoField(primary_key=True)
    source = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    body = models.TextField(null=True, blank=True)
    url = models.URLField(unique=True)
    parsed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'news'
