import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import BaseCommand
from django.utils import timezone

from accounts.models import BackupRecord, log_action


def sha256_path(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = 'Create a timestamped forensic database backup without overwriting the active database.'

    def add_arguments(self, parser):
        parser.add_argument('--created-by', type=int, default=None)

    def handle(self, *args, **options):
        backup_dir = Path(settings.BASE_DIR) / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        db = settings.DATABASES['default']
        engine = db.get('ENGINE', '')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        creator = None
        if options.get('created_by'):
            creator = User.objects.filter(pk=options['created_by']).first()

        record = None
        try:
            if engine.endswith('sqlite3'):
                source = Path(db['NAME'])
                if not source.exists():
                    raise FileNotFoundError(f'SQLite database does not exist: {source}')
                target = backup_dir / f'forensic_sqlite_{timestamp}.sqlite3'
                if target.resolve() == source.resolve():
                    raise RuntimeError('Refusing to overwrite the active database.')
                shutil.copy2(source, target)
            elif engine.endswith('postgresql'):
                target = backup_dir / f'forensic_postgresql_{timestamp}.dump'
                cmd = [
                    os.getenv('PG_DUMP_BIN', 'pg_dump'),
                    '-Fc',
                    '-f', str(target),
                    '-h', db.get('HOST') or 'localhost',
                    '-p', str(db.get('PORT') or '5432'),
                    '-U', db.get('USER') or '',
                    db.get('NAME') or '',
                ]
                env = os.environ.copy()
                if db.get('PASSWORD'):
                    env['PGPASSWORD'] = db['PASSWORD']
                subprocess.run(cmd, check=True, env=env)
            else:
                raise RuntimeError(f'Unsupported database engine for backup: {engine}')

            record = BackupRecord.objects.create(
                filename=str(target),
                database_engine=engine,
                size_bytes=target.stat().st_size,
                checksum_sha256=sha256_path(target),
                created_by=creator,
                status='success',
            )
            log_action(creator, 'backup_created', target=target.name)
            self.stdout.write(self.style.SUCCESS(f'Backup created: {target}'))
            self.stdout.write(f'SHA-256: {record.checksum_sha256}')
        except Exception as exc:
            BackupRecord.objects.create(
                filename='',
                database_engine=engine,
                created_by=creator,
                status='failed',
                error_message=str(exc),
            )
            raise
