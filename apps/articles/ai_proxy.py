import os
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from apps.core.permissions import IsAuthor, IsInternalService
from .models import Article
from .pdf_jobs import PdfJobConflict, admit_pdf_job, apply_pdf_callback, mark_pdf_job_running


def _ai_service_urls():
    configured_url = os.getenv("AI_SERVICE_URL", "").strip()
    urls = [
        "http://localhost:8001/api",
        "http://127.0.0.1:8001/api",
        "http://host.docker.internal:8001/api",
        "http://ai-service:8001/api",
        "http://deepscholar-ai:8001/api",
    ]
    if configured_url:
        urls.insert(0, configured_url.rstrip('/'))
    deduped_urls = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduped_urls.append(url)
            seen.add(url)
    return deduped_urls


def _ai_service_headers():
    headers = {'Content-Type': 'application/json'}
    internal_key = os.getenv('INTERNAL_SERVICE_KEY', '').strip()
    if internal_key:
        headers['X-Internal-Service-Key'] = internal_key
    return headers


def _can_process_article(user, article):
    if user.is_staff or user.is_superuser:
        return True
    author_profile = getattr(user, 'author_profile', None)
    return bool(author_profile and article.authors.filter(pk=author_profile.pk).exists())


def _safe_json(response):
    try:
        payload = response.json()
        return payload if isinstance(payload, dict) else {'error': 'AI Service returned an invalid response.'}
    except ValueError:
        return {'error': 'AI Service returned an invalid response.'}


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAuthor])
def trigger_pdf_pipeline(request):
    """
    Proxy endpoint: receives the PDF trigger from the Frontend and forwards it
    to the AI Service.
    
    Expected body: { pdf_url, slug, article_id }
    """
    payload = request.data
    slug = payload.get('slug')
    
    # Force article_id to be an integer
    try:
        article_id = int(payload.get('article_id'))
    except (TypeError, ValueError):
        print(f"[Backend Proxy] ERROR: Invalid article_id: {payload.get('article_id')}")
        return Response({"error": "Invalid article_id"}, status=400)

    try:
        article = Article.objects.prefetch_related('authors').get(id=article_id, is_active=True)
    except Article.DoesNotExist:
        return Response({"error": "Article not found"}, status=404)

    user = request.user
    if not _can_process_article(user, article):
        raise PermissionDenied("You do not have permission to process this article.")

    if slug and slug != article.slug:
        return Response({"error": "Slug does not match the article"}, status=400)

    requested_pdf_url = payload.get('pdf_url')
    if requested_pdf_url and requested_pdf_url != article.pdf_url:
        return Response({"error": "PDF URL does not match the article"}, status=400)

    idempotency_key = request.headers.get("Idempotency-Key", "")
    try:
        job, _created = admit_pdf_job(article.id, user, idempotency_key)
    except PdfJobConflict as exc:
        return Response({"error": str(exc.detail)}, status=exc.status_code)

    if job.status == "completed":
        return Response(
            {"task_id": str(job.task_id), "status": "completed", "article_id": article.id, "slug": article.slug},
            status=200,
        )
    if job.status == "failed":
        return Response(
            {"task_id": str(job.task_id), "status": "failed", "error_code": job.error_code},
            status=409,
        )

    mark_pdf_job_running(job)
    payload = {
        "task_id": str(job.task_id),
        "generation": job.generation,
        "content_revision": job.content_revision,
        "idempotency_key": job.idempotency_key,
        "article_id": article.id,
        "slug": article.slug,
        "pdf_url": article.pdf_url,
    }

    print(f"[Backend Proxy] TRIGGER: Starting PDF job {job.task_id} for ID {article_id} (slug: {slug})")

    try:
        ai_response = None
        attempted_urls = _ai_service_urls()
        for base_url in attempted_urls:
            try:
                ai_response = requests.post(
                    f"{base_url}/pdf/upload?sync=False",
                    json=payload,
                    headers=_ai_service_headers(),
                    timeout=30
                )
                break
            except requests.exceptions.ConnectionError:
                continue

        if ai_response is None:
            return Response(
                {"error": f"AI Service is not reachable. Tried: {', '.join(attempted_urls)}"},
                status=503
            )

        if ai_response.ok:
            data = _safe_json(ai_response)

            if data.get('task_id') == str(job.task_id):
                return Response(data, status=202)
            return Response({"error": "AI Service returned a missing or mismatched task ID."}, status=502)
        else:
            print(f"[Backend Proxy] ERROR: AI Service returned HTTP {ai_response.status_code}: {ai_response.text}")
            return Response(_safe_json(ai_response), status=ai_response.status_code)

    except requests.exceptions.Timeout:
        return Response(
            {"error": "AI Service processing timed out. The extraction is likely still running in the background."},
            status=504
        )
    except requests.exceptions.ConnectionError:
        return Response(
            {"error": "AI Service is not reachable. Ensure the AI service is running."},
            status=503
        )
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(["POST"])
@permission_classes([IsInternalService])
def pdf_pipeline_callback(request):
    try:
        result = apply_pdf_callback(request.data)
    except PdfJobConflict as exc:
        return Response({"error": str(exc.detail)}, status=exc.status_code)
    return Response(result, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAuthor])
def pdf_pipeline_status(request):
    """Return a PDF job status after verifying the requesting author's ownership."""
    task_id = (request.query_params.get('task_id') or '').strip()
    if not task_id:
        return Response({'error': 'task_id is required'}, status=400)

    try:
        ai_response = None
        attempted_urls = _ai_service_urls()
        for base_url in attempted_urls:
            try:
                ai_response = requests.get(
                    f"{base_url}/pdf/status",
                    params={'task_id': task_id},
                    headers=_ai_service_headers(),
                    timeout=10,
                )
                break
            except requests.exceptions.ConnectionError:
                continue

        if ai_response is None:
            return Response({'error': 'AI Service is not reachable.'}, status=503)

        data = _safe_json(ai_response)
        if ai_response.status_code == 404:
            return Response({'detail': 'PDF task not found or expired.'}, status=404)
        if not ai_response.ok:
            return Response(data, status=ai_response.status_code)

        try:
            article_id = int(data.get('article_id'))
            article = Article.objects.prefetch_related('authors').get(
                id=article_id,
                is_active=True,
            )
        except (TypeError, ValueError, Article.DoesNotExist):
            return Response({'detail': 'PDF task not found or expired.'}, status=404)

        if not _can_process_article(request.user, article):
            return Response({'detail': 'PDF task not found or expired.'}, status=404)

        return Response(data, status=ai_response.status_code)
    except requests.exceptions.Timeout:
        return Response({'error': 'AI Service status check timed out.'}, status=504)
    except requests.exceptions.ConnectionError:
        return Response({'error': 'AI Service is not reachable.'}, status=503)
    except Exception:
        return Response({'error': 'Unable to read PDF processing status.'}, status=500)
