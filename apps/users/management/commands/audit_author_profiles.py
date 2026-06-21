from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.models import Author, User
from apps.users.services import become_author


class Command(BaseCommand):
    help = "Audit and optionally repair inconsistencies between User.role and Author profiles."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Repair inconsistent records. Without this flag the command is report-only.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        fix = options['fix']
        missing_profiles = User.objects.filter(role=User.ROLE_AUTHOR, author_profile__isnull=True)
        wrong_roles = User.objects.filter(role=User.ROLE_USER, author_profile__isnull=False)

        missing_count = missing_profiles.count()
        wrong_role_count = wrong_roles.count()
        fixed_profiles = 0
        fixed_roles = 0

        self.stdout.write(f"Authors missing profiles: {missing_count}")
        self.stdout.write(f"Users with profiles but role=user: {wrong_role_count}")

        if fix:
            for user in missing_profiles.iterator():
                become_author(user=user)
                fixed_profiles += 1

            fixed_roles = wrong_roles.update(role=User.ROLE_AUTHOR)

        unlinked_authors = Author.objects.filter(user__isnull=True).count()
        self.stdout.write(f"Unlinked author records left unchanged: {unlinked_authors}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Audit complete. Fixed profiles: {fixed_profiles}; fixed roles: {fixed_roles}."
            )
        )
