import uuid
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.users.models import Author, Notification


User = get_user_model()


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = [
            "id",
            "author_code",
            "affiliation",
            "bio",
            "total_score",
            "follower_count",
            "created_at",
            "is_active",
        ]


class UserSerializer(serializers.ModelSerializer):
    author_profile = AuthorSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "user_code",
            "email",
            "full_name",
            "gender",
            "address",
            "role",
            "avatar_url",
            "provider",
            "provider_id",
            "is_active",
            "created_at",
            "author_profile",
        ]
        read_only_fields = ["id", "user_code", "provider", "provider_id", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    affiliation = serializers.CharField(required=False, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "full_name",
            "gender",
            "address",
            "role",
            "avatar_url",
            "affiliation",
            "bio",
        ]

    def create(self, validated_data):
        """
        Create new user with optional author profile
        1. Extract author profile fields
        2. Create user with user_code
        3. Create Author profile if role=author
        """
        affiliation = validated_data.pop('affiliation', '')
        bio = validated_data.pop('bio', '')
        password = validated_data.pop('password')
        role = validated_data.get('role', 'user')
        
        # Generate user_code
        validated_data['user_code'] = f"USR-{uuid.uuid4().hex[:8].upper()}"
        
        user = User.objects.create_user(password=password, **validated_data)
        
        if role == 'author':
            author_code = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
            Author.objects.create(
                user=user,
                author_code=author_code,
                affiliation=affiliation,
                bio=bio
            )
            
        return user


class SocialAuthSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    provider_id = serializers.CharField(max_length=255)
    avatar_url = serializers.CharField(required=False, allow_blank=True)
    role = serializers.CharField(required=False, default="user")

    def save(self, provider):
        """
        TODO: Get or create user from social auth provider
        1. Get/create user with email
        2. Update provider credentials
        3. Create Author profile if needed
        """
        # TODO: Implementation
        return None


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "reference_id", "message", "is_read", "created_at"]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        """
        Add custom claims to JWT token
        - email
        - role
        """
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        return token

    def validate(self, attrs):
        """
        Validate credentials and return user data with token
        """
        data = super().validate(attrs)
        
        user_serializer = UserSerializer(self.user)
        data['user'] = user_serializer.data
        return data