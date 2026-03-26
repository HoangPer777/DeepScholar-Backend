import os
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Article


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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
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

    print(f"[Backend Proxy] TRIGGER: Starting AI sync for ID {article_id} (slug: {slug})")

    try:
        ai_response = None
        attempted_urls = _ai_service_urls()
        for base_url in attempted_urls:
            try:
                ai_response = requests.post(
                    f"{base_url}/pdf/upload?sync=True",
                    json=payload,
                    timeout=300
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
            data = ai_response.json()

            inner_data = data.get('data', {})
            title = inner_data.get('title')
            abstract = inner_data.get('abstract')
            content = inner_data.get('content')

            # Force an update even if title is short (use fallback if empty)
            update_title = title if (title and len(title) > 2) else "Untitled Article (Extracted)"
            
            updated_count = Article.objects.filter(id=article_id).update(
                title=update_title,
                abstract=abstract or "No abstract extracted.",
                content=content or "No content extracted."
            )
            
            if updated_count > 0:
                print(f"[Backend Proxy] SUCCESS: Article {article_id} updated in DB.")
                print(f"[Backend Proxy] Summary: {len(content) if content else 0} chars saved.")
            else:
                print(f"[Backend Proxy] WARNING: Article {article_id} not found during update.")
            
            return Response(data, status=ai_response.status_code)
        else:
            print(f"[Backend Proxy] ERROR: AI Service returned HTTP {ai_response.status_code}: {ai_response.text}")
            return Response(ai_response.json(), status=ai_response.status_code)

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
