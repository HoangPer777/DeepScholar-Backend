from rest_framework import serializers
from .models import Article
from apps.users.models import Author


class AuthorBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['id', 'author_code', 'affiliation']


class ArticleListSerializer(serializers.ModelSerializer):
    author = AuthorBasicSerializer(read_only=True)

    class Meta:
        model = Article
        fields = ['id', 'slug', 'title', 'abstract', 'author', 'view_count', 'created_at']


class ArticleDetailSerializer(serializers.ModelSerializer):
    author = AuthorBasicSerializer(read_only=True)

    class Meta:
        model = Article
        fields = '__all__'


class ArticleCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ['slug', 'title', 'abstract', 'content', 'pdf_url']