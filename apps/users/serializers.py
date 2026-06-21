import uuid
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.users.models import Author, Notification
from apps.users.services import become_author


User = get_user_model()


class AuthorSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, obj):
        return obj.user.avatar_url if obj.user else None
    
    class Meta:
        model = Author
        fields = [
            "id",
            "author_code",
            "full_name",
            "avatar_url",
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
        read_only_fields = [
            "id", "user_code", "role", "provider", "provider_id",
            "is_active", "created_at", "author_profile",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default=User.ROLE_USER)
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

    @transaction.atomic
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
        
        if role == User.ROLE_AUTHOR:
            user, _, _ = become_author(
                user=user,
                affiliation=affiliation,
                bio=bio,
            )
            
        return user


class SocialAuthSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    provider_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    avatar_url = serializers.CharField(required=False, allow_blank=True)

    def save(self, provider):
        """
        Get or create user from social auth provider
        1. Get/create user with email
        2. Update provider credentials
        3. Create Author profile if needed
        """
        email = self.validated_data.get('email')
        full_name = self.validated_data.get('full_name', '')
        provider_id = self.validated_data.get('provider_id', '')
        avatar_url = self.validated_data.get('avatar_url', '')

        user = User.objects.filter(email=email).first()
        if not user:
            # Create user
            user_code = f"USR-{uuid.uuid4().hex[:8].upper()}"
            # Give a random password since they login via social
            user_password = uuid.uuid4().hex
            user = User.objects.create_user(
                email=email,
                password=user_password,
                full_name=full_name,
                user_code=user_code,
                provider=provider,
                provider_id=provider_id,
                avatar_url=avatar_url,
                role=User.ROLE_USER
            )
        else:
            # Update provider info if needed
            update_fields = []
            if user.provider == 'local':
                user.provider = provider
                user.provider_id = provider_id
                update_fields += ['provider', 'provider_id']

            if update_fields:
                user.save(update_fields=update_fields)

        return user


class BecomeAuthorSerializer(serializers.Serializer):
    author_name = serializers.CharField(max_length=255, required=False, allow_blank=True, trim_whitespace=True)
    affiliation = serializers.CharField(max_length=255, required=False, allow_blank=True, trim_whitespace=True)
    bio = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    accepted_author_terms = serializers.BooleanField()

    def validate_accepted_author_terms(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the author publishing terms.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        return become_author(
            user=user,
            author_name=self.validated_data.get('author_name', ''),
            affiliation=self.validated_data.get('affiliation', ''),
            bio=self.validated_data.get('bio', ''),
        )


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "actor", "verb", "target_content_type", "target_object_id", "is_read", "created_at"]
        read_only_fields = ["id", "actor", "created_at"]


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
