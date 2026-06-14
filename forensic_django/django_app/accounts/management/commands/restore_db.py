from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = 'Restore the database from a JSON fixture.'

    def add_arguments(self, parser):
        parser.add_argument('fixture_path')

    def handle(self, *args, **options):
        call_command('loaddata', options['fixture_path'])
        self.stdout.write(self.style.SUCCESS('Database restore completed.'))
