"""
Custom runserver command that respects the BACKEND_PORT env / Django setting.

Usage (any of these work):
    manage.py runserver                  # uses BACKEND_PORT from .env (default 8000)
    manage.py runserver 9000             # explicit port overrides env
    manage.py runserver 0.0.0.0:9000    # explicit addr:port overrides env
    BACKEND_PORT=9000 manage.py runserver
"""

from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticFilesRunserverCommand,
)
from django.conf import settings


class Command(StaticFilesRunserverCommand):
    help = "Start the development server (port from BACKEND_PORT env if not given)."

    def add_arguments(self, parser):
        super().add_arguments(parser)

    def execute(self, *args, **options):
        # Only inject the port when the caller did NOT provide an addrport argument
        # (Django sets addrport to '' when it is absent from argv).
        if not options.get('addrport'):
            port = getattr(settings, 'BACKEND_PORT', 8000)
            options['addrport'] = str(port)
        super().execute(*args, **options)
