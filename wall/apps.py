from django.apps import AppConfig


class WallConfig(AppConfig):
    name = 'wall'

    def ready(self):
        import wall.signals  # noqa: F401
