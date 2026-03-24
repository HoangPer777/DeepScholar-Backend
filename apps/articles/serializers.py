from rest_framework import serializers
from .models import Article
from apps.users.models import Author


class AuthorBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['id', 'author_code', 'affiliation']


class ArticleListSerializer(serializers.ModelSerializer):
    authors = AuthorBasicSerializer(many=True, read_only=True)

    class Meta:
        model = Article
        fields = ['id', 'slug', 'title', 'abstract', 'authors', 'view_count', 'like_count', 'bookmark_count', 'share_count', 'created_at']


class ArticleDetailSerializer(serializers.ModelSerializer):
    authors = AuthorBasicSerializer(many=True, read_only=True)

    class Meta:
        model = Article
        fields = '__all__'


class ArticleCreateUpdateSerializer(serializers.ModelSerializer):
    co_authors = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Article
        fields = ['id', 'slug', 'title', 'abstract', 'content', 'pdf_url', 'co_authors']
        read_only_fields = ['id']

    def create(self, validated_data):
        co_authors_ids = validated_data.pop('co_authors', [])
        article = super().create(validated_data)
        return self._handle_co_authors(article, co_authors_ids)

    def update(self, instance, validated_data):
        co_authors_ids = validated_data.pop('co_authors', None)
        article = super().update(instance, validated_data)
        if co_authors_ids is not None:
            self._handle_co_authors(article, co_authors_ids, update=True)
        return article

    def _handle_co_authors(self, article, co_authors_ids, update=False):
        from .models import ArticleAuthor
        from apps.users.models import Author
        
        request = self.context.get('request')
        primary_author = getattr(request.user, 'author_profile', None) if request else None

        if not update and primary_author:
            ArticleAuthor.objects.create(
                article=article, author=primary_author, order=1, is_corresponding=True
            )
        elif update:
            ArticleAuthor.objects.filter(article=article, order__gt=1).delete()

        if co_authors_ids:
            order = 2
            for author_id in co_authors_ids:
                try:
                    author = Author.objects.get(id=author_id)
                    if author != primary_author:
                        ArticleAuthor.objects.get_or_create(
                            article=article, author=author,
                            defaults={'order': order, 'is_corresponding': False}
                        )
                        order += 1
                except Author.DoesNotExist:
                    continue
        return article