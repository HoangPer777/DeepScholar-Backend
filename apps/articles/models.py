from django.db import models
from apps.users.models import Author

class Article(models.Model):
    authors = models.ManyToManyField(Author, related_name='articles', through='ArticleAuthor')
    slug = models.SlugField(max_length=255, unique=True, allow_unicode=True)
    title = models.TextField()
    abstract = models.TextField(blank=True, null=True) 
    content = models.TextField(blank=True, null=True)
    pdf_url = models.TextField(blank=True, null=True)
    view_count = models.IntegerField(default=0)
    like_count = models.IntegerField(default=0)
    bookmark_count = models.IntegerField(default=0)
    share_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'articles'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['title']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return str(self.title)

class ArticleAuthor(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1)
    is_corresponding = models.BooleanField(default=False)

    class Meta:
        db_table = 'article_authors'
        ordering = ['order']
        unique_together = ('article', 'author')

    def __str__(self):
        return f"{self.author} - {self.article}"
