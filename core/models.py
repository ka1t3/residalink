from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
import secrets


def make_invite_code():
    return secrets.token_hex(3).upper()  # ex: A3F2B1


class Residence(models.Model):
    name = models.CharField("Nom", max_length=120)
    address = models.CharField("Adresse", max_length=255, blank=True)
    invite_code = models.CharField("Code d'invitation", max_length=12, unique=True, default=make_invite_code)
    created_at = models.DateTimeField(auto_now_add=True)
    is_demo = models.BooleanField("Résidence de démonstration", default=False)

    class Meta:
        verbose_name = "Résidence"

    def __str__(self):
        return self.name


class User(AbstractUser):
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, null=True, blank=True, related_name="members")
    display_name = models.CharField("Nom affiché", max_length=80)
    lot = models.CharField("Lot / appartement", max_length=30, blank=True)
    notify_by_email = models.BooleanField("Recevoir des emails", default=True)
    notify_incidents = models.BooleanField("Incidents (nouveaux et suivis)", default=True)
    notify_alerts = models.BooleanField("Alertes de la résidence", default=True)
    notify_replies = models.BooleanField("Réponses à mes messages", default=True)
    is_demo = models.BooleanField("Compte de démonstration", default=False)

    class Meta:
        verbose_name = "Utilisateur"

    def __str__(self):
        return self.display_name or self.username

    @property
    def is_council(self):
        return self.groups.filter(name="conseil_syndical").exists() or self.is_staff

    @property
    def public_name(self):
        return f"{self.display_name}" + (f" · lot {self.lot}" if self.lot else "")


class PublicRequestCooldown(models.Model):
    """Limitation de débit simple par IP pour les endpoints publics.

    Stockage en base (pas de cache mémoire : multi-workers gunicorn et
    redéploiements). Les entrées obsolètes sont purgées à chaque écriture
    (pas de cron requis).
    """

    key = models.CharField("Clé d'endpoint", max_length=40)
    ip = models.GenericIPAddressField("Adresse IP")
    last_at = models.DateTimeField("Dernier passage")

    class Meta:
        verbose_name = "Limitation de débit (endpoint public)"
        verbose_name_plural = "Limitations de débit (endpoints publics)"
        unique_together = ("key", "ip")

    def __str__(self):
        return f"{self.key} · {self.ip} · {self.last_at:%d/%m %H:%M}"


class ResidenceModule(models.Model):
    MODULES = [
        ("incidents", "Centre d'incidents"),
        ("wall", "Mur d'actualité"),
        ("directory", "Carnet de santé"),
    ]
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, related_name="modules")
    module = models.CharField(max_length=30, choices=MODULES)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("residence", "module")
        verbose_name = "Module de résidence"

    def __str__(self):
        return f"{self.residence} · {self.get_module_display()} ({'actif' if self.enabled else 'inactif'})"


@receiver(post_save, sender=Residence)
def create_default_modules(sender, instance, created, **kwargs):
    """Active les modules par défaut dès la création d'une résidence (admin ou bootstrap)."""
    if created:
        for module, _ in ResidenceModule.MODULES:
            ResidenceModule.objects.get_or_create(residence=instance, module=module, defaults={"enabled": True})
