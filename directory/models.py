from django.db import models
from core.models import Residence


class Contact(models.Model):
    CATEGORIES = [
        ("urgence", "Urgences"),
        ("conseil", "Conseil syndical"),
        ("syndic", "Syndic"),
        ("entreprise", "Entreprises"),
    ]
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, related_name="contacts")
    category = models.CharField("Catégorie", max_length=20, choices=CATEGORIES)
    name = models.CharField("Nom", max_length=120)
    role = models.CharField("Rôle / spécialité", max_length=120, blank=True)
    phone = models.CharField("Téléphone", max_length=30, blank=True)
    email = models.EmailField("Email", blank=True)
    notes = models.TextField("Notes", blank=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Contact"

    def __str__(self):
        return self.name


class PracticalInfo(models.Model):
    """Informations permanentes de la résidence (horaires, accès, règles de vie...)."""
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, related_name="infos")
    title = models.CharField("Titre", max_length=120)
    content = models.TextField("Contenu")
    order = models.PositiveSmallIntegerField("Ordre d'affichage", default=0)

    class Meta:
        ordering = ["order", "title"]
        verbose_name = "Info pratique"
        verbose_name_plural = "Infos pratiques"

    def __str__(self):
        return self.title


class WorkRecord(models.Model):
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, related_name="works")
    title = models.CharField("Intitulé", max_length=200)
    date = models.DateField("Date")
    company = models.CharField("Entreprise", max_length=120, blank=True)
    amount = models.DecimalField("Montant (€)", max_digits=10, decimal_places=2, null=True, blank=True)
    description = models.TextField("Description", blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Travaux"

    def __str__(self):
        return self.title
