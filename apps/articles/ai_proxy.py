import os
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://host.docker.internal:8001/api")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_pdf_pipeline(request):
    """
    Proxy endpoint: receives the PDF trigger from the Frontend and forwards it
    to the AI Service. This avoids the Frontend needing to know the AI service's
    internal Docker network address.
    
    Expected body: { pdf_url, slug, article_id }
    """
    payload = request.data

    try:
        ai_response = requests.post(
            f"{AI_SERVICE_URL}/pdf/upload",
            json=payload,
            timeout=10
        )
        return Response(ai_response.json(), status=ai_response.status_code)
    except requests.exceptions.ConnectionError:
        return Response(
            {"error": "AI Service is not reachable. Ensure the AI service is running."},
            status=503
        )
    except Exception as e:
        return Response({"error": str(e)}, status=500)
