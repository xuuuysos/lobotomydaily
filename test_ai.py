import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lobotomynews.settings")
django.setup()

import traceback
from core.ai_utils import client

try:
    response = client.chat.completions.create(
        model='qwen/qwen3.6-plus:free',
        messages=[{'role': 'user', 'content': 'hello'}],
        response_format={ "type": "json_object" }
    )
    print("Success:", response)
except Exception as e:
    traceback.print_exc()
