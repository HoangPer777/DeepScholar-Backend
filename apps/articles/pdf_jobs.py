import hashlib
import json
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from .models import Article, PdfProcessingJob


class PdfJobConflict(APIException):
    status_code = 409
    default_detail = "A PDF processing job conflicts with the current article revision."
    default_code = "pdf_job_conflict"


def _fingerprint(article: Article) -> str:
    value = json.dumps(
        {"article_id": article.pk, "pdf_url": article.pdf_url},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@transaction.atomic
def admit_pdf_job(article_id: int, requester, idempotency_key: str):
    try:
        key = str(uuid.UUID(idempotency_key))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PdfJobConflict("A valid Idempotency-Key UUID is required.") from exc

    article = Article.objects.select_for_update().get(pk=article_id, is_active=True)
    fingerprint = _fingerprint(article)
    existing = PdfProcessingJob.objects.select_for_update().filter(
        article=article,
        requester=requester,
        idempotency_key=key,
    ).first()
    if existing:
        if existing.input_fingerprint != fingerprint:
            raise PdfJobConflict("The idempotency key was already used with different PDF input.")
        if (
            existing.status in {
                PdfProcessingJob.Status.QUEUED,
                PdfProcessingJob.Status.RUNNING,
                PdfProcessingJob.Status.ARTICLE_SAVED,
                PdfProcessingJob.Status.EMBEDDING,
            }
            and existing.deadline_at <= timezone.now()
        ):
            existing.status = PdfProcessingJob.Status.FAILED
            existing.error_code = "pdf_job_timeout"
            existing.retryable = False
            existing.save(update_fields=["status", "error_code", "retryable", "updated_at"])
        return existing, False

    active_jobs = PdfProcessingJob.objects.select_for_update().filter(
        article=article,
        status__in=[
            PdfProcessingJob.Status.QUEUED,
            PdfProcessingJob.Status.RUNNING,
            PdfProcessingJob.Status.ARTICLE_SAVED,
            PdfProcessingJob.Status.EMBEDDING,
        ],
    )
    now = timezone.now()
    active_jobs.filter(deadline_at__lte=now).update(
        status=PdfProcessingJob.Status.FAILED,
        error_code="pdf_job_timeout",
        retryable=False,
    )
    active = active_jobs.filter(deadline_at__gt=now).first()
    if active:
        return active, False

    deadline_at = now + timedelta(minutes=30)
    article.pdf_generation += 1
    article.pdf_generation_deadline = deadline_at
    article.save(update_fields=["pdf_generation", "pdf_generation_deadline"])
    job = PdfProcessingJob.objects.create(
        article=article,
        requester=requester,
        idempotency_key=key,
        input_fingerprint=fingerprint,
        generation=article.pdf_generation,
        content_revision=article.content_revision,
        deadline_at=deadline_at,
    )
    return job, True


def mark_pdf_job_running(job: PdfProcessingJob) -> None:
    PdfProcessingJob.objects.filter(
        task_id=job.task_id,
        status=PdfProcessingJob.Status.QUEUED,
    ).update(status=PdfProcessingJob.Status.RUNNING)


@transaction.atomic
def apply_pdf_callback(payload: dict) -> dict:
    task_id = payload.get("task_id")
    try:
        task_id = uuid.UUID(str(task_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PdfJobConflict("A valid task_id is required.") from exc

    try:
        job_article_id = PdfProcessingJob.objects.only("article_id").get(task_id=task_id).article_id
    except PdfProcessingJob.DoesNotExist as exc:
        raise NotFound("PDF task not found.") from exc

    article = Article.objects.select_for_update().get(pk=job_article_id)
    job = PdfProcessingJob.objects.select_for_update().get(task_id=task_id)
    if job.article_id != article.pk:
        raise PdfJobConflict("PDF task article identity changed.")
    if (
        job.status not in {PdfProcessingJob.Status.FAILED, PdfProcessingJob.Status.COMPLETED}
        and job.deadline_at <= timezone.now()
    ):
        raise PdfJobConflict("The PDF job has expired.")
    try:
        generation = int(payload.get("generation"))
        content_revision = int(payload.get("content_revision"))
    except (TypeError, ValueError) as exc:
        raise PdfJobConflict("A valid generation and content_revision are required.") from exc

    if generation != job.generation or generation != article.pdf_generation:
        raise PdfJobConflict("The PDF callback belongs to a stale generation.")
    if content_revision != job.content_revision or content_revision != article.content_revision:
        raise PdfJobConflict("The article was edited after this PDF job started.")

    event = payload.get("event")
    if event == "article_saved":
        fields = {name: payload.get(name) for name in ("title", "abstract", "content")}
        if not all(isinstance(value, str) for value in fields.values()):
            raise PdfJobConflict("Extracted article fields must be strings.")
        if not fields["title"].strip() or not fields["content"].strip():
            raise PdfJobConflict("Extracted title and content must not be empty.")
        digest = hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if job.article_saved:
            if job.callback_payload_hash != digest:
                raise PdfJobConflict("A different callback payload was already applied.")
        else:
            if job.status in {PdfProcessingJob.Status.FAILED, PdfProcessingJob.Status.COMPLETED}:
                raise PdfJobConflict("The PDF job is already terminal.")
            article.title = fields["title"]
            article.abstract = fields["abstract"]
            article.content = fields["content"]
            article.save(update_fields=["title", "abstract", "content", "updated_at"])
            job.article_saved = True
            job.callback_payload_hash = digest
            job.status = PdfProcessingJob.Status.ARTICLE_SAVED
            job.save(update_fields=["article_saved", "callback_payload_hash", "status", "updated_at"])
    elif event == "embeddings_saved":
        if not job.article_saved:
            raise PdfJobConflict("Article data must be saved before embeddings.")
        if job.status == PdfProcessingJob.Status.FAILED:
            raise PdfJobConflict("The PDF job is already failed.")
        job.embeddings_saved = True
        job.status = PdfProcessingJob.Status.COMPLETED
        job.error_code = ""
        job.retryable = False
        job.save(update_fields=["embeddings_saved", "status", "error_code", "retryable", "updated_at"])
    elif event == "failed":
        if job.status == PdfProcessingJob.Status.COMPLETED:
            raise PdfJobConflict("The PDF job is already completed.")
        job.status = PdfProcessingJob.Status.FAILED
        job.error_code = str(payload.get("error_code") or "pdf_processing_failed")[:80]
        job.retryable = bool(payload.get("retryable", False))
        job.save(update_fields=["status", "error_code", "retryable", "updated_at"])
    else:
        raise PdfJobConflict("Unsupported PDF callback event.")

    return {
        "task_id": str(job.task_id),
        "generation": job.generation,
        "status": job.status,
        "article_saved": job.article_saved,
        "embeddings_saved": job.embeddings_saved,
    }
