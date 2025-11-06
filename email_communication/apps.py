from django.apps import AppConfig


class EmailCommunicationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'email_communication'
    verbose_name = 'Email Communication System'
    
    def ready(self):
        # Import signals if needed in future
        pass
