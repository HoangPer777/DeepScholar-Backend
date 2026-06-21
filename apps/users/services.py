import uuid

from django.db import IntegrityError, transaction

from apps.users.models import Author, User


def generate_author_code():
    """Generate an author code and retry in the unlikely event of a collision."""
    for _ in range(10):
        code = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
        if not Author.objects.filter(author_code=code).exists():
            return code
    raise RuntimeError("Could not generate a unique author code.")


@transaction.atomic
def become_author(*, user, author_name='', affiliation='', bio=''):
    """Atomically promote a user and create (or reuse) their author profile."""
    locked_user = User.objects.select_for_update().get(pk=user.pk)

    author = Author.objects.filter(user=locked_user).first()
    created = False
    if author is None:
        for _ in range(10):
            try:
                # The nested atomic block provides a savepoint, so a uniqueness
                # race does not leave the outer promotion transaction broken.
                with transaction.atomic():
                    author, created = Author.objects.get_or_create(
                        user=locked_user,
                        defaults={
                            'author_code': generate_author_code(),
                            'author_name': author_name or locked_user.full_name,
                            'affiliation': affiliation,
                            'bio': bio,
                        },
                    )
                break
            except IntegrityError:
                author = Author.objects.filter(user=locked_user).first()
                if author is not None:
                    created = False
                    break
        else:
            raise RuntimeError("Could not create a unique author profile.")

    if locked_user.role != User.ROLE_AUTHOR:
        locked_user.role = User.ROLE_AUTHOR
        locked_user.save(update_fields=['role'])

    return locked_user, author, created
