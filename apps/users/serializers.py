import uuid
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.users.models import Author, Notification


User = get_user_model()


class AuthorSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = Author
        fields = [
            "id",
            "author_code",
            "full_name",
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
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    provider_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    avatar_url = serializers.CharField(required=False, allow_blank=True)
    role = serializers.CharField(required=False, default="user")

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
        role = self.validated_data.get('role', 'user')

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
                role=role
            )
            
            if role == 'author':
                author_code = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
                Author.objects.create(
                    user=user,
                    author_code=author_code,
                    bio="",
                    affiliation=""
                )
        else:
            # Update provider info if needed
            update_fields = []
            if user.provider == 'local':
                user.provider = provider
                user.provider_id = provider_id
                update_fields += ['provider', 'provider_id']

            # Upgrade role to author if requested and not already author
            if role == 'author' and user.role != 'author':
                user.role = 'author'
                update_fields.append('role')

            if update_fields:
                user.save(update_fields=update_fields)

            # Create Author profile if role is author but profile missing
            if user.role == 'author' and not Author.objects.filter(user=user).exists():
                author_code = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
                Author.objects.create(
                    user=user,
                    author_code=author_code,
                    bio="",
                    affiliation=""
                )

        return user


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