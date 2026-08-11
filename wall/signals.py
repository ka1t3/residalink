from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import PostPhoto


@receiver(post_delete, sender=PostPhoto)
def delete_post_photo_file(sender, instance, **kwargs):
    """Supprime le fichier physique quand un PostPhoto est supprimé.

    Fonctionne aussi lors des suppressions en cascade (Post → photos).
    """
    if instance.image:
        instance.image.delete(save=False)
