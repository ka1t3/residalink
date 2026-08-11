from django.apps import AppConfig


class IncidentsConfig(AppConfig):
    name = 'incidents'

    def ready(self):
        import incidents.signals  # noqa: F401
