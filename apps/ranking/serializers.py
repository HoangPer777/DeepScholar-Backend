from rest_framework import serializers

from apps.users.models import Author


class AuthorRankingSerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = (
            "rank", "id", "author_code", "full_name", "affiliation",
            "avatar_url", "article_count", "like_count", "commenter_count",
            "total_score",
        )

    def get_rank(self, obj):
        return self.context["rank"]

    def get_avatar_url(self, obj):
        return obj.user.avatar_url if obj.user else None
