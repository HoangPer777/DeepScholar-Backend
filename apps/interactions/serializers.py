from rest_framework import serializers

from apps.interactions.models import Comment
from apps.users.serializers import UserSerializer


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "article", "user", "content", "created_at"]
        read_only_fields = ["id", "article", "user", "created_at"]
        # TODO: Add validation for content length and profanity