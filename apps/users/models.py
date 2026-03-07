from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class CustomUserManager(BaseUserManager):
    """TODO: Implement custom user manager for email-based auth"""
    def create_user(self, email, password=None, **extra_fields):
        # TODO: Implement user creation logic
        pass

    def create_superuser(self, email, password=None, **extra_fields):
        # TODO: Implement superuser creation logic
        pass


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model with OAuth support"""
    user_code = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    GENDER_CHOICES = [('male', 'Male'), ('female', 'Female'), ('other', 'Other')]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    role = models.CharField(max_length=20, default='user')
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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='author_profile')
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    total_score = models.IntegerField(default=0)  # Ranking score
    follower_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'authors'


class Notification(models.Model):
    """User notifications for interactions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=50)  # like, comment, follow, etc.
    reference_id = models.IntegerField(blank=True, null=True)  # ID of related object
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
