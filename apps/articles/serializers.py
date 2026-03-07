from rest_framework import serializers

from apps.articles.models import Article, ArticleChunk
from apps.users.models import Author
from apps.users.serializers import AuthorSerializer


class ArticleChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleChunk
        fields = ["id", "chunk_index", "content"]


class ArticleSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    author_id = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.filter(is_active=True),
        source="author",
        write_only=True,
        required=False,
    )
    chunks = ArticleChunkSerializer(many=True, read_only=True)
    comments_count = serializers.IntegerField(source="comments.count", read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "author",
            "author_id",
            "slug",
            "title",
            "abstract",
            "content",
            "pdf_url",
            "view_count",
            "like_count",
            "bookmark_count",
            "share_count",
            "created_at",
            "updated_at",
            "is_active",
            "chunks",
            "comments_count",
        ]
        read_only_fields = [
            "id",
            "view_count",
            "like_count",
            "bookmark_count",
            "share_count",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        """
        TODO: Create article with author validation
        1. Get author from validated_data or request.user.author_profile
        2. Validate author exists and is active
        3. Set article author and save
        """
        # TODO: Implementation
        return None