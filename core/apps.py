"""
Application configuration and background scheduler.
"""

import os
import threading
import time
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Only run background scheduler in Django's main process, avoiding duplicate threads in dev mode (reloader)
        if os.environ.get('RUN_MAIN') == 'true':
            threading.Thread(target=self.start_background_scheduler, daemon=True).start()

    def start_background_scheduler(self):
        # Delay imports until apps are fully loaded
        from django.core.management import call_command
        
        # Sleep for 5 seconds to let the server boot up completely
        time.sleep(5)
        
        while True:
            try:
                print("\n[Scheduler] Starting scheduled background news parsing...")
                # Pre-fetch news for the last 7 days to keep feed fresh
                call_command('parse_news', days=7, limit=5, clear=False)
                print("[Scheduler] Scheduled background news parsing completed successfully.\n")
            except Exception as e:
                print(f"\n[Scheduler] Error during scheduled background news parsing: {e}\n")
            
            # Sleep for 30 minutes
            time.sleep(1800)
