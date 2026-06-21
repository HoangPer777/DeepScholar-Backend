from time import monotonic

from django.core.management.base import BaseCommand, CommandError

from apps.ranking.services import recalculate_authors
from apps.users.models import Author


class Command(BaseCommand):
    help = "Recalculate author ranking scores from source interactions."

    def add_arguments(self, parser):
        parser.add_argument("--author-id", type=int)

    def handle(self, *args, **options):
        started = monotonic()
        queryset = Author.objects.all()
        author_id = options.get("author_id")
        if author_id is not None:
            queryset = queryset.filter(pk=author_id)
            if not queryset.exists():
                raise CommandError(f"Author {author_id} does not exist.")

        ids = list(queryset.values_list("id", flat=True))
        recalculate_authors(ids)
        elapsed = monotonic() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(ids)} author(s), succeeded {len(ids)}, failed 0 in {elapsed:.3f}s."
            )
        )
