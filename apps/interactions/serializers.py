from rest_framework import serializers

from apps.interactions.models import Comment
from apps.users.models import Notification
from apps.users.serializers import UserSerializer


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "article", "user", "content", "parent", "replies", "created_at"]
        read_only_fields = ["id", "article", "user", "replies", "created_at"]

    def get_replies(self, obj):
        # Only serialize one level deep (top-level comments expose their replies)
        if obj.parent is None:
            qs = obj.replies.select_related('user__author_profile').order_by('created_at')
            return CommentSerializer(qs, many=True, context=self.context).data
        return []

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Content must not be empty.")
        if len(value) > 2000:
            raise serializers.ValidationError("Content must be 2000 characters or fewer.")
        return value


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "actor", "verb", "target_content_type", "target_object_id", "is_read", "created_at"]
        read_only_fields = ["id", "actor", "verb", "target_content_type", "target_object_id", "created_at"]
