from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ranking.services import calculate_ranking_metrics
from apps.users.models import Author
from apps.ranking.serializers import AuthorRankingSerializer


class AuthorRankingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = Author.objects.filter(is_active=True).select_related("user")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(author_code__icontains=search)
                | Q(author_name__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(affiliation__icontains=search)
            )

        authors = list(queryset)
        metrics = calculate_ranking_metrics([author.id for author in authors])
        authors.sort(
            key=lambda author: (
                -metrics[author.id].total_score,
                -metrics[author.id].like_count,
                -metrics[author.id].commenter_count,
                -metrics[author.id].article_count,
                author.id,
            )
        )
        try:
            page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
            page_number = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            page_size, page_number = 20, 1

        paginator = Paginator(authors, page_size)
        try:
            page = paginator.page(page_number)
        except EmptyPage:
            page = paginator.page(paginator.num_pages or 1)

        start_rank = page.start_index() if paginator.count else 0
        results = []
        for offset, author in enumerate(page.object_list):
            results.append(
                AuthorRankingSerializer(
                    author,
                    context={
                        "request": request,
                        "metrics": metrics[author.id],
                        "rank": start_rank + offset,
                    },
                ).data
            )

        def page_url(number):
            query = request.query_params.copy()
            query["page"] = number
            query["page_size"] = page_size
            return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")

        return Response(
            {
                "count": paginator.count,
                "next": page_url(page.next_page_number()) if page.has_next() else None,
                "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
                "results": results,
            }
        )
