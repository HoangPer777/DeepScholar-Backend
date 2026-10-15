import uuid

from django.conf import settings
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
    pdf_generation = models.PositiveIntegerField(default=0)
    pdf_generation_deadline = models.DateTimeField(null=True, blank=True)
    content_revision = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'articles'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['title']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return str(self.title)


class PdfProcessingJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        ARTICLE_SAVED = "article_saved", "Article saved"
        EMBEDDING = "embedding", "Embedding"
        FAILED = "failed", "Failed"
        COMPLETED = "completed", "Completed"

    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="pdf_jobs")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    idempotency_key = models.CharField(max_length=64)
    input_fingerprint = models.CharField(max_length=64)
    generation = models.PositiveIntegerField()
    content_revision = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    article_saved = models.BooleanField(default=False)
    embeddings_saved = models.BooleanField(default=False)
    callback_payload_hash = models.CharField(max_length=64, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    retryable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline_at = models.DateTimeField()

    class Meta:
        db_table = "pdf_processing_jobs"
        constraints = [
            models.UniqueConstraint(
                fields=["article", "requester", "idempotency_key"],
                name="uniq_pdf_job_request_key",
            ),
        ]
        indexes = [models.Index(fields=["article", "status"], name="pdf_job_article_status_idx")]

    def __str__(self):
        return f"PDF job {self.task_id} ({self.status})"

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
