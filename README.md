# DeepScholar Backend Service

Django REST API for scientific article management, user authentication, and author ranking system.

## Overview

This service handles:
- User and author profile management
- Article CRUD operations and metadata
- Interactions (likes, comments, bookmarks, shares)
- Author ranking and scoring
- JWT authentication + OAuth 2.0 placeholders (Google, Facebook)
- Notification system

## 🚀 Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 16 (or use Docker)

### Installation

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Or (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Run migrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

## 📁 Project Structure

```
backend-service/
├── apps/
│   ├── users/              # User, Author, Notification models
│   │   ├── models.py       # User (custom AbstractBaseUser), Author
│   │   ├── views.py        # Auth, user profile, author endpoints
│   │   ├── serializers.py  # JWT, OAuth, user serialization
│   │   └── urls.py         # Auth routes: register, login, oauth
│   ├── articles/           # Article management
│   │   ├── models.py       # Article, ArticleChunk
│   │   ├── views.py        # CRUD, upload URL, view counting
│   │   ├── serializers.py  # Article serialization with metadata
│   │   └── urls.py         # Article endpoints
│   ├── interactions/       # Like, Comment, Bookmark, Share
│   │   ├── models.py       # Like, Comment, Bookmark, ArticleShare, AuthorFollow
│   │   ├── views.py        # Toggle endpoints, comment CRUD
│   │   ├── serializers.py  # Comment, notification data
│   │   └── urls.py         # Interaction routes
│   └── ranking/            # Author scoring
│       ├── services.py     # recalculate_author_score() function
│       ├── views.py        # Author ranking endpoint
│       └── urls.py         # Ranking routes
├── config/
│   ├── settings.py         # Django configuration, database, apps
│   ├── urls.py             # Root URL router
│   ├── wsgi.py
│   └── asgi.py
├── manage.py               # Django CLI
├── requirements.txt        # Dependencies
├── .env.example            # Environment variables template
├── Dockerfile              # Container image
└── dev.sqlite3             # Local SQLite (dev only)
```

## 🔧 Configuration

### Environment Variables (.env)

```env
DJANGO_SECRET_KEY=your-secret-key-change-in-production
DJANGO_DEBUG=True               # Set to False in production
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend-service
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://localhost:8001
DATABASE_URL=postgresql://deepscholar:deepscholar@localhost:5432/deepscholar
```

## 📚 API Endpoints

### Authentication
- `POST /api/v1/auth/register/` - Register new user
- `POST /api/v1/auth/login/` - JWT login
- `POST /api/v1/auth/google/` - Google OAuth (placeholder)
- `POST /api/v1/auth/facebook/` - Facebook OAuth (placeholder)
- `GET /api/v1/auth/me/` - Authenticated user profile

### Users
- `GET/PUT /api/v1/users/<id>/` - User profile

### Authors
- `GET /api/v1/authors/<id>/` - Author public profile
- `POST /api/v1/authors/<id>/follow/` - Toggle author follow
- `GET /api/v1/authors/ranking/` - Author ranking (top authors)

### Articles
- `GET /api/v1/articles/` - List articles (filterable, searchable, paginated)
- `POST /api/v1/articles/` - Create article
- `GET /api/v1/articles/upload_url/` - Get presigned S3 URL (placeholder)
- `GET /api/v1/articles/<slug>/` - Article detail (increments view count)
- `PUT /api/v1/articles/<slug>/` - Update article
- `DELETE /api/v1/articles/<slug>/` - Soft delete article

### Interactions
- `POST /api/v1/articles/<id>/like/` - Toggle like article
- `POST /api/v1/articles/<id>/bookmark/` - Toggle bookmark article
- `GET /api/v1/articles/<id>/comments/` - List comments
- `POST /api/v1/articles/<id>/comments/` - Post comment

### Notifications
- `GET /api/v1/notifications/` - User notifications
- `POST /api/v1/notifications/<id>/read/` - Mark notification as read

## 🗄️ Database Schema

### Key Models

**User** (Custom AbstractBaseUser)
- user_code (public identifier)
- email (unique)
- full_name, gender, address
- role (user, author, admin)
- avatar_url, provider (oauth provider), provider_id
- is_active, is_staff

**Author** (OneToOne with User)
- author_code (public identifier)
- affiliation, bio
- total_score (ranking points)
- follower_count

**Article**
- slug (unique)
- title, abstract, content, pdf_url
- view_count, like_count, bookmark_count, share_count
- author_id (FK)
- created_at, updated_at

**Interactions**
- Like (article + user unique constraint)
- Comment (article + user)
- Bookmark (article + user unique constraint)
- ArticleShare (article + user)
- AuthorFollow (follower + followed author)

**Notification**
- user_id (FK)
- type (like, comment, follow, etc)
- reference_id (object being interacted with)
- is_read, created_at

## 🔄 Ranking System

Author scoring formula (in `apps/ranking/services.py`):
```
total_score = (
    view_count * 1 +
    like_count * 5 +
    bookmark_count * 3 +
    share_count * 4 +
    follower_count * 2
)
```

Updated automatically when articles are viewed, liked, bookmarked, shared, or followed.

## 🧪 Development Commands

```bash
# Run tests (if configured)
python manage.py test

# Run migrations
python manage.py migrate

# Make migrations
python manage.py makemigrations

# Django shell
python manage.py shell

# Run server with reload
python manage.py runserver 0.0.0.0:8000

# Access Django admin
# http://localhost:8000/admin
```

## 🐳 Docker Usage

```bash
# Build image
docker build -t deepscholar-backend .

# Run container (requires PostgreSQL)
docker run -p 8001:8000 \
  -e DATABASE_URL=postgresql://... \
  deepscholar-backend
```

Or via docker-compose from root directory:
```bash
docker compose up backend-service
```

## 📤 Deployment Checklist

- [ ] Set `DJANGO_DEBUG=False`
- [ ] Generate strong `DJANGO_SECRET_KEY`
- [ ] Configure `DJANGO_ALLOWED_HOSTS`
- [ ] Use PostgreSQL (not SQLite)
- [ ] Set up proper CORS origins
- [ ] Configure S3 or alternative storage
- [ ] Set up OAuth credentials (Google/Facebook)
- [ ] Configure email backend for notifications
- [ ] Set up database backups
- [ ] Enable HTTPS

## 📝 Next Steps

Future enhancements:
- Real OAuth 2.0 integration (Google, Facebook token verification)
- S3 integration for PDF storage
- Email notifications
- Advanced search and filtering
- API rate limiting
- Caching layer (Redis)
- GraphQL layer
