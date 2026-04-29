from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.articles.models import Article
from apps.users.models import Author, Notification
from apps.interactions.models import Like, Bookmark, ArticleShare, AuthorFollow, Comment


# ---------------------------------------------------------------------------
# Like count maintenance
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Like, dispatch_uid='interactions.like_post_save_count')
def update_article_like_count(sender, instance, created, **kwargs):
    """Increment like_count atomically when a new Like is created."""
    if created:
        Article.objects.filter(pk=instance.article_id).update(
            like_count=F('like_count') + 1
        )


@receiver(post_delete, sender=Like, dispatch_uid='interactions.like_post_delete_count')
def update_article_like_count_on_delete(sender, instance, **kwargs):
    """Decrement like_count atomically when a Like is deleted."""
    Article.objects.filter(pk=instance.article_id).update(
        like_count=F('like_count') - 1
    )


# ---------------------------------------------------------------------------
# Bookmark count maintenance
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Bookmark, dispatch_uid='interactions.bookmark_post_save_count')
def update_article_bookmark_count(sender, instance, created, **kwargs):
    """Increment bookmark_count atomically when a new Bookmark is created."""
    if created:
        Article.objects.filter(pk=instance.article_id).update(
            bookmark_count=F('bookmark_count') + 1
        )


@receiver(post_delete, sender=Bookmark, dispatch_uid='interactions.bookmark_post_delete_count')
def update_article_bookmark_count_on_delete(sender, instance, **kwargs):
    """Decrement bookmark_count atomically when a Bookmark is deleted."""
    Article.objects.filter(pk=instance.article_id).update(
        bookmark_count=F('bookmark_count') - 1
    )


# ---------------------------------------------------------------------------
# Share count maintenance
# ---------------------------------------------------------------------------

@receiver(post_save, sender=ArticleShare, dispatch_uid='interactions.articleshare_post_save_count')
def update_article_share_count(sender, instance, created, **kwargs):
    """Increment share_count atomically when a new ArticleShare is created."""
    if created:
        Article.objects.filter(pk=instance.article_id).update(
            share_count=F('share_count') + 1
        )


# ---------------------------------------------------------------------------
# Author follower count maintenance
# ---------------------------------------------------------------------------

@receiver(post_save, sender=AuthorFollow, dispatch_uid='interactions.authorfollow_post_save_count')
def update_author_follower_count(sender, instance, created, **kwargs):
    """Increment follower_count atomically when a new AuthorFollow is created."""
    if created:
        Author.objects.filter(pk=instance.followed_author_id).update(
            follower_count=F('follower_count') + 1
        )


@receiver(post_delete, sender=AuthorFollow, dispatch_uid='interactions.authorfollow_post_delete_count')
def update_author_follower_count_on_delete(sender, instance, **kwargs):
    """Decrement follower_count atomically when an AuthorFollow is deleted."""
    Author.objects.filter(pk=instance.followed_author_id).update(
        follower_count=F('follower_count') - 1
    )


# ---------------------------------------------------------------------------
# Notification creation signals
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Like, dispatch_uid='interactions.like_post_save_notify')
def notify_on_like(sender, instance, created, **kwargs):
    """Create notifications for article authors when a new Like is created."""
    if not created:
        return
    article = instance.article
    actor = instance.user
    content_type = ContentType.objects.get_for_model(Article)
    notifications = [
        Notification(
            recipient=aa.author.user,
            actor=actor,
            verb="liked your article",
            target_content_type=content_type,
            target_object_id=article.pk,
        )
        for aa in article.articleauthor_set.select_related('author__user')
        if aa.author.user is not None and aa.author.user != actor
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


@receiver(post_save, sender=Comment, dispatch_uid='interactions.comment_post_save_notify')
def notify_on_comment(sender, instance, created, **kwargs):
    """Create notifications on new comment: article authors or parent comment author."""
    if not created:
        return
    actor = instance.user
    content_type = ContentType.objects.get_for_model(Comment)
    notifications = []

    if instance.parent is None:
        # Top-level comment — notify article authors
        for aa in instance.article.articleauthor_set.select_related('author__user'):
            recipient = aa.author.user
            if recipient is not None and recipient != actor:
                notifications.append(Notification(
                    recipient=recipient,
                    actor=actor,
                    verb="commented on your article",
                    target_content_type=content_type,
                    target_object_id=instance.pk,
                ))
    else:
        # Reply — notify parent comment author
        recipient = instance.parent.user
        if recipient != actor:
            notifications.append(Notification(
                recipient=recipient,
                actor=actor,
                verb="replied to your comment",
                target_content_type=content_type,
                target_object_id=instance.pk,
            ))

    if notifications:
        Notification.objects.bulk_create(notifications)


@receiver(post_save, sender=AuthorFollow, dispatch_uid='interactions.authorfollow_post_save_notify')
def notify_on_follow(sender, instance, created, **kwargs):
    """Create a notification for the followed author when a new follow is created."""
    if not created:
        return
    recipient = instance.followed_author.user
    actor = instance.follower_author.user
    if recipient is None or actor is None or recipient == actor:
        return
    content_type = ContentType.objects.get_for_model(Author)
    Notification.objects.create(
        recipient=recipient,
        actor=actor,
        verb="started following you",
        target_content_type=content_type,
        target_object_id=instance.followed_author_id,
    )
