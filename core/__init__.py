import os
import django

# Set default settings module for Django if not already set
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'init.settings')

# Initialize Django apps to allow safe imports of models and forms
try:
    django.setup()
except Exception:
    pass
