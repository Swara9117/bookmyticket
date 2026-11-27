"""
WSGI config for bookmyticket project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bookmyticket.settings')

application = get_wsgi_application()

# Vercel has no release command. On a Postgres deploy, apply pending migrations
# once per instance so a redeploy picks up new columns without a manual shell.
# Set AUTO_MIGRATE=0 to turn this off after the schema is current.
def _apply_migrations():
    if os.environ.get('AUTO_MIGRATE', '1') != '1':
        return
    if not os.environ.get('DATABASE_URL'):
        return
    import logging
    from django.core.management import call_command
    log = logging.getLogger('bookmyticket.migrate')
    try:
        call_command('migrate', interactive=False, verbosity=1)
    except Exception:
        log.exception('Automatic migrate failed. Fix the database, then redeploy.')

_apply_migrations()

app = application
