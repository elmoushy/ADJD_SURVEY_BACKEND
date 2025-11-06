from django.apps import AppConfig


class SurveysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'surveys'
    verbose_name = 'Surveys'
    
    def ready(self):
        """Initialize signals when the app is ready."""
        import surveys.signals  # noqa
