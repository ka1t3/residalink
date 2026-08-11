from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import IncidentPhoto


@receiver(post_delete, sender=IncidentPhoto)
def delete_incident_photo_file(sender, instance, **kwargs):
    """Supprime le fichier physique quand un IncidentPhoto est supprimé.

    Fonctionne aussi lors des suppressions en cascade (Incident → photos).
    """
    if instance.image:
        instance.image.delete(save=False)
