from django.core.management.base import BaseCommand

from movies.services import process_background_jobs


class Command(BaseCommand):
    help = 'Release expired seat holds and retry queued ticket emails.'

    def handle(self, *args, **options):
        result = process_background_jobs()
        self.stdout.write(str(result))
