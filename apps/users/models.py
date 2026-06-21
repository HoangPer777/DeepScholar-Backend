from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class CustomUserManager(BaseUserManager):
    """Custom user manager for email-based auth and standard create_user"""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        
        # Ensure user_code is present, or error will be caught on save if REQUIRED_FIELDS enforces it,
        # but typically handled at serializer/view level.
        user = self.model(email=email, **extra_fields)
        
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model with OAuth support"""
    ROLE_USER = 'user'
    ROLE_AUTHOR = 'author'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_AUTHOR, 'Author'),
    ]
    user_code = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    GENDER_CHOICES = [('male', 'Male'), ('female', 'Female'), ('other', 'Other')]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_USER)
    avatar_url = models.TextField(blank=True, null=True)
    provider = models.CharField(max_length=50, default='local')  # local, google, facebook
    provider_id = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['user_code']

    class Meta:
        db_table = 'users'


class Author(models.Model):
    """Author profile for academic users"""
    author_code = models.CharField(max_length=50, unique=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, related_name='author_profile', null=True, blank=True)
    author_name = models.CharField(max_length=255, blank=True, null=True)
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    total_score = models.IntegerField(default=0)  # Ranking score
    follower_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    @property
    def full_name(self):
        if self.user and self.user.full_name:
            return self.user.full_name
        return self.author_name or self.author_code

    class Meta:
        db_table = 'authors'


class Notification(models.Model):
    """User notifications for interactions"""
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    verb = models.CharField(max_length=255)
    target_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('target_content_type', 'target_object_id')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read'], name='notif_recipient_is_read_idx'),
            models.Index(fields=['recipient', 'created_at'], name='notif_recipient_created_at_idx'),
        ]
