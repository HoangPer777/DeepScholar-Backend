from rest_framework import generics, permissions

from apps.users.models import Author
from apps.users.serializers import AuthorSerializer


class AuthorRankingView(generics.ListAPIView):
    """TODO: List top-ranked authors"""
    serializer_class = AuthorSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # TODO: Order by total_score desc
        pass