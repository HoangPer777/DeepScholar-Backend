import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("articles", "0004_remove_article_author_articleauthor_article_authors"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="pdf_generation",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="article",
            name="pdf_generation_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="content_revision",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="PdfProcessingJob",
            fields=[
                ("task_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=64)),
                ("input_fingerprint", models.CharField(max_length=64)),
                ("generation", models.PositiveIntegerField()),
                ("content_revision", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("article_saved", "Article saved"), ("embedding", "Embedding"), ("failed", "Failed"), ("completed", "Completed")], default="queued", max_length=20)),
                ("article_saved", models.BooleanField(default=False)),
                ("embeddings_saved", models.BooleanField(default=False)),
                ("callback_payload_hash", models.CharField(blank=True, max_length=64)),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("retryable", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deadline_at", models.DateTimeField()),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pdf_jobs", to="articles.article")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "pdf_processing_jobs"},
        ),
        migrations.AddConstraint(
            model_name="pdfprocessingjob",
            constraint=models.UniqueConstraint(fields=("article", "requester", "idempotency_key"), name="uniq_pdf_job_request_key"),
        ),
        migrations.AddIndex(
            model_name="pdfprocessingjob",
            index=models.Index(fields=["article", "status"], name="pdf_job_article_status_idx"),
        ),
    ]
