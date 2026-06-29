from django.core.management import BaseCommand


class Command(BaseCommand):
    help = 'Compatibility wrapper. Use create_forensic_backup for safe database backups.'

    def handle(self, *args, **options):
        from django.core.management import call_command

        call_command('create_forensic_backup')
