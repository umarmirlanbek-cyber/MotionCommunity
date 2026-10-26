from django.apps import AppConfig
from django.db.models.signals import post_delete, pre_save


class MotionAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'motion_app'

    def ready(self):
        from . import translations
        from .models import file_fields, delete_replaced_files, delete_files
        for model in self.get_models():
            if file_fields(model):
                pre_save.connect(delete_replaced_files, sender=model)
                post_delete.connect(delete_files, sender=model)