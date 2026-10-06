from time import monotonic

from django.core.management.base import BaseCommand, CommandError

from apps.ranking.services import recalculate_authors
from apps.users.models import Author


class Command(BaseCommand):
    help = "Recalculate author ranking scores from source interactions."

    def add_arguments(self, parser):
        parser.add_argument("--author-id", type=int)
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        started = monotonic()
        queryset = Author.objects.all()
        author_id = options.get("author_id")
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be greater than zero.")

        if author_id is not None:
            queryset = queryset.filter(pk=author_id)
            if not queryset.exists():
                raise CommandError(f"Author {author_id} does not exist.")

        processed = 0
        batch = []
        for current_author_id in queryset.order_by("id").values_list("id", flat=True).iterator(
            chunk_size=batch_size
        ):
            batch.append(current_author_id)
            if len(batch) >= batch_size:
                recalculate_authors(batch)
                processed += len(batch)
                batch = []

        if batch:
            recalculate_authors(batch)
            processed += len(batch)

        elapsed = monotonic() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} author(s), succeeded {processed}, failed 0 in {elapsed:.3f}s."
            )
        )
