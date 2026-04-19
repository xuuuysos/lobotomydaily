import os
import django
from django.core.management import call_command

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'init.settings')
    django.setup()
    
    print("Starting news parsing via management command...")
    # By default, parse the last 7 days with a limit of 10 per day, without clearing.
    call_command('parse_news', days=7, limit=10, clear=False)
    print("Done.")

