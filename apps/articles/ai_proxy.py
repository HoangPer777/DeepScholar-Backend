import os
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Article
from .serializers import ArticleDetailSerializer


AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://host.docker.internal:8001/api")


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
        # We call the AI service and wait (timeout 5 min for large PDFs)
        ai_response = requests.post(
            f"{AI_SERVICE_URL}/pdf/upload?sync=True",
            json=payload,
            timeout=300
        )
        
        if ai_response.ok:
            data = ai_response.json()
            
            # Extract values from the nested response
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
