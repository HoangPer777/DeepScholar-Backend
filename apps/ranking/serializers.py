from rest_framework import serializers

from apps.users.models import Author


class AuthorRankingSerializer(serializers.ModelSerializer):
    rank = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    article_count = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField()
    commenter_count = serializers.SerializerMethodField()
    total_score = serializers.SerializerMethodField()

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

    def get_article_count(self, obj):
        return self.context["metrics"].article_count

    def get_like_count(self, obj):
        return self.context["metrics"].like_count

    def get_commenter_count(self, obj):
        return self.context["metrics"].commenter_count

    def get_total_score(self, obj):
        return self.context["metrics"].total_score

