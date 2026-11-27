try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover - package installed via requirements
    celery_app = None

__all__ = ('celery_app',)
