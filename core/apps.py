from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Enregistre l'ouvreur HEIF/HEIC pour Pillow une seule fois, au
        # démarrage. Sans lui, `Image.open()` ne sait pas décoder un fichier
        # HEIC (capture directe sur téléphone) : les photos seraient refusées
        # ou stockées sans pouvoir être relues. Ne pas déplacer dans un
        # module importé plusieurs fois.
        import pillow_heif
        pillow_heif.register_heif_opener()
