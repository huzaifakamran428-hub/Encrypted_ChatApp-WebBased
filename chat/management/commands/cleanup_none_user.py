"""
Management command: python manage.py cleanup_none_user

Removes the ghost user account with username 'None' that was created
by a session/registration bug, along with all their messages.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Delete the ghost user with username 'None' and their messages"

    def handle(self, *args, **options):
        try:
            ghost = User.objects.get(username='None')
            # Delete their sent/received messages first (CASCADE should handle it, but be explicit)
            sent = ghost.sent_messages.count()
            recv = ghost.received_messages.count()
            ghost.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted ghost user 'None' (had {sent} sent, {recv} received messages)."
                )
            )
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING("No ghost user 'None' found — nothing to do."))
