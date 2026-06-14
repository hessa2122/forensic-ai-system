from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.utils import timezone


class Command(BaseCommand):
    help = 'Dump the database to a timestamped JSON fixture in backups/.'

    def handle(self, *args, **options):
        backup_dir = Path(settings.BASE_DIR) / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'db_backup_{timestamp}.json'
        call_command('dumpdata', indent=2, output=str(backup_path))
        self.stdout.write(self.style.SUCCESS(f'Database backup saved to {backup_path}'))
