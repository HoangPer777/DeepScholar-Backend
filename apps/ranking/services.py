from apps.users.models import Author


def recalculate_author_score(author: Author) -> int:
    """
    TODO: Calculate author ranking score based on:
    - view_count * 1
    - like_count * 5
    - bookmark_count * 3
    - share_count * 4
    - follower_count * 2
    """
    # TODO: Implement scoring logic
    return 0