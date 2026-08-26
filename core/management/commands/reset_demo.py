"""Purge et recrée intégralement la résidence de démonstration (idempotent).

Usage : uv run manage.py reset_demo

Pensé pour être appelé quotidiennement (cron / tâche planifiée Coolify) afin
que chaque visiteur découvre une démo « fraîche ».
"""
import os
import random
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Residence, User
from directory.models import Contact, PracticalInfo, WorkRecord
from incidents.models import Incident, IncidentCategory, IncidentPhoto, IncidentUpdate
from wall.models import Comment, Post, PostPhoto

DEMO_RESIDENCE_NAME = "Résidence Démo (Les Tilleuls)"
DEMO_USERNAME = "demo"

# 6 catégories par défaut créées par `bootstrap.py` — réutilisées ici plutôt
# que réimplémentées, cf. AGENTS.MD (« ne pas réimplémenter une
# fonctionnalité déjà présente »).
DEFAULT_CATEGORIES = [
    ("Ascenseur", "arrow-up-down", 1),
    ("Fuite d'eau", "droplet", 2),
    ("Éclairage", "lightbulb", 3),
    ("Portail / porte", "door-open", 4),
    ("Propreté", "spray-can", 5),
    ("Autre", "wrench", 6),
]

# 2-3 photos d'exemple committées dans le dépôt (aucune image distante :
# la CSP n'autorise que `img-src 'self' data: blob:`).
DEMO_PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "demo_photos")
DEMO_PHOTO_FILES = ["ascenseur.jpg", "fuite.jpg", "facade.jpg"]

DEMO_RESIDENTS = [
    ("Camille Petit", "A12"),
    ("Julien Rocher", "A34"),
    ("Aïcha Benali", "B02"),
    ("Marc Lefevre", "B15"),
    ("Sophie Dubois", "B21"),
    ("Nadia Cherif", "C04"),
    ("Thomas Moreau", "C11"),
    ("Elise Faure", "C23"),
]


class Command(BaseCommand):
    help = "Purge puis recrée la résidence de démonstration avec des données fictives."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._purge()
            residence = self._create_residence_and_groups()
            residents = self._create_residents(residence)
            demo_user = self._create_demo_account(residence)
            self._create_incidents(residence, residents)
            self._create_posts(residence, residents)
            self._create_directory(residence)

        self.stdout.write(self.style.SUCCESS(
            f"Démo prête : résidence « {residence.name} », compte « {demo_user.username} »."
        ))

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------
    def _purge(self):
        """Supprime l'ancienne résidence de démo, s'il en existe une."""
        # PIÈGE (cf. AGENTS.MD « Médias / photos ») : la suppression en
        # cascade d'une Residence peut emprunter, selon les cas, un chemin
        # « fast delete » de Django qui ne charge pas les instances enfants
        # en mémoire et n'émet donc PAS le signal `post_delete` sur
        # IncidentPhoto/PostPhoto. Les fichiers physiques resteraient alors
        # orphelins sur le volume persistant, et s'accumuleraient à chaque
        # exécution quotidienne de cette commande.
        #
        # On supprime donc TOUJOURS les photos une par une, objet par objet
        # (jamais `queryset.delete()` en masse), et SEULEMENT ENSUITE la
        # Residence elle-même :
        #   a) IncidentPhoto un par un
        #   b) PostPhoto un par un
        #   c) puis la Residence (qui cascade sur le reste : incidents,
        #      posts, utilisateurs démo, contacts…), sans plus aucun
        #      fichier image à nettoyer.
        for demo_residence in Residence.objects.filter(is_demo=True):
            for photo in IncidentPhoto.objects.filter(incident__residence=demo_residence):
                photo.delete()  # déclenche le signal post_delete → fichier supprimé
            for photo in PostPhoto.objects.filter(post__residence=demo_residence):
                photo.delete()  # idem
            demo_residence.delete()

    # ------------------------------------------------------------------
    # Résidence, groupes, catégories
    # ------------------------------------------------------------------
    def _create_residence_and_groups(self):
        # `bootstrap.py` crée sa Residence avec `get_or_create(name=...)`,
        # pas `create()` : l'appeler plusieurs fois ne duplique donc pas de
        # résidence. On réutilise malgré tout uniquement les `get_or_create`
        # (groupes, catégories) directement ici plutôt que d'appeler la
        # commande `bootstrap` en entier, pour rester maître de la création
        # de la Residence démo (nom stable + flag `is_demo=True`) sans
        # dépendre de sa signature (`name` positionnel, message de sortie…).
        Group.objects.get_or_create(name="conseil_syndical")
        Group.objects.get_or_create(name="resident")
        for name, icon, order in DEFAULT_CATEGORIES:
            IncidentCategory.objects.get_or_create(name=name, defaults={"icon": icon, "order": order})

        residence, _ = Residence.objects.get_or_create(
            name=DEMO_RESIDENCE_NAME,
            defaults={"address": "12 allée des Tilleuls, 69003 Lyon"},
        )
        residence.is_demo = True
        residence.address = "12 allée des Tilleuls, 69003 Lyon"
        residence.save()
        # Les ResidenceModule sont créés automatiquement par le signal
        # `post_save` sur Residence (core/models.py) dès la création.
        return residence

    # ------------------------------------------------------------------
    # Résidents fictifs
    # ------------------------------------------------------------------
    def _create_residents(self, residence):
        residents = []
        for i, (display_name, lot) in enumerate(DEMO_RESIDENTS, start=1):
            username = f"demo-resident-{i}"
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "residence": residence,
                    "display_name": display_name,
                    "lot": lot,
                    "is_demo": True,
                    "email": "",
                },
            )
            user.set_unusable_password()
            user.save()
            residents.append(user)

        # Le premier résident est membre du conseil syndical, comme un vrai
        # premier inscrit de résidence (cf. core/views.py::join).
        council_group, _ = Group.objects.get_or_create(name="conseil_syndical")
        council_group.user_set.add(residents[0], residents[1])
        return residents

    def _create_demo_account(self, residence):
        """Compte utilisé par la route /demo/ : membre du conseil syndical
        pour voir aussi les écrans réservés au CS (le middleware
        DemoReadOnlyMiddleware bloque de toute façon toute action)."""
        demo_user, _ = User.objects.update_or_create(
            username=DEMO_USERNAME,
            defaults={
                "residence": residence,
                "display_name": "Visiteur Démo",
                "lot": "D07",
                "is_demo": True,
                "email": "",
            },
        )
        demo_user.set_unusable_password()
        demo_user.save()
        Group.objects.get_or_create(name="conseil_syndical")[0].user_set.add(demo_user)
        return demo_user

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------
    def _create_incidents(self, residence, residents):
        now = timezone.now()
        categories = list(IncidentCategory.objects.all())

        incidents_data = [
            ("Ascenseur bloqué entre le 2e et le 3e", "signale", 2),
            ("Fuite sous l'évier du local vélo", "pris_en_compte", 9),
            ("Ampoule grillée dans le hall B", "en_cours", 15),
            ("Porte du portail qui ne se referme plus", "resolu", 30),
        ]

        for title, status, days_ago in incidents_data:
            created_at = now - timedelta(days=days_ago)
            category = random.choice(categories)
            author = random.choice(residents)
            incident = Incident.objects.create(
                residence=residence,
                author=author,
                category=category,
                title=title,
                description="Signalement fictif généré pour la démonstration.",
                location="Hall / parties communes",
                status="signale",
            )
            # `created_at` a `auto_now_add=True` : on l'étale après coup via
            # un simple UPDATE (pas de suppression, donc aucun risque lié
            # au signal post_delete).
            Incident.objects.filter(pk=incident.pk).update(created_at=created_at)

            self._add_incident_journal(incident, status, created_at, residents)

            if status != "signale":
                Incident.objects.filter(pk=incident.pk).update(status=status)
            if status == "resolu":
                Incident.objects.filter(pk=incident.pk).update(resolved_at=now - timedelta(days=days_ago - 3))

            if random.random() < 0.7:
                self._attach_photo(incident)

    def _add_incident_journal(self, incident, final_status, created_at, residents):
        order = ["signale", "pris_en_compte", "en_cours", "resolu"]
        target_index = order.index(final_status)
        step_date = created_at
        previous = "signale"
        for step in order[1:target_index + 1]:
            step_date = step_date + timedelta(days=random.randint(1, 5))
            update = IncidentUpdate.objects.create(
                incident=incident,
                author=random.choice(residents),
                old_status=previous,
                new_status=step,
                message="Mise à jour fictive de démonstration.",
            )
            IncidentUpdate.objects.filter(pk=update.pk).update(created_at=step_date)
            previous = step

    def _attach_photo(self, incident):
        filename = random.choice(DEMO_PHOTO_FILES)
        path = os.path.join(DEMO_PHOTOS_DIR, filename)
        photo = IncidentPhoto(incident=incident)
        with open(path, "rb") as fh:
            photo.image.save(filename, File(fh), save=True)

    # ------------------------------------------------------------------
    # Mur (posts)
    # ------------------------------------------------------------------
    def _create_posts(self, residence, residents):
        now = timezone.now()
        posts_data = [
            ("alerte", "Attention, l'eau chaude sera coupée demain de 9h à 12h pour maintenance.", 3, True),
            ("info", "Le nouveau digicode du portail arrière est actif depuis lundi.", 10, False),
            ("evenement", "Pot de voisins organisé samedi 14h dans la cour intérieure, tous bienvenus !", 18, False),
            ("entraide", "Je recherche quelqu'un pour arroser mes plantes la semaine du 15, je pars en vacances.", 6, False),
        ]

        for post_type, content, days_ago, pinned in posts_data:
            created_at = now - timedelta(days=days_ago)
            post = Post.objects.create(
                residence=residence,
                author=random.choice(residents),
                type=post_type,
                content=content,
                pinned=pinned,
            )
            Post.objects.filter(pk=post.pk).update(created_at=created_at)

            for _ in range(random.randint(1, 3)):
                comment = Comment.objects.create(
                    post=post,
                    author=random.choice(residents),
                    content="Merci pour l'information !",
                )
                Comment.objects.filter(pk=comment.pk).update(
                    created_at=created_at + timedelta(hours=random.randint(1, 48))
                )

            if random.random() < 0.5:
                self._attach_post_photo(post)

    def _attach_post_photo(self, post):
        filename = random.choice(DEMO_PHOTO_FILES)
        path = os.path.join(DEMO_PHOTOS_DIR, filename)
        photo = PostPhoto(post=post)
        with open(path, "rb") as fh:
            photo.image.save(filename, File(fh), save=True)

    # ------------------------------------------------------------------
    # Carnet (« Information générale »)
    # ------------------------------------------------------------------
    def _create_directory(self, residence):
        Contact.objects.create(
            residence=residence, category="urgence", name="Pompiers", phone="18",
        )
        Contact.objects.create(
            residence=residence, category="urgence", name="Gardien de la résidence",
            phone="06 00 00 00 00", role="Astreinte 24h/24",
        )
        Contact.objects.create(
            residence=residence, category="syndic", name="Cabinet Syndic Exemple",
            phone="04 00 00 00 00", email="contact@syndic-exemple.example",
        )
        Contact.objects.create(
            residence=residence, category="conseil", name="Conseil syndical",
            role="Contact via le mur de la résidence",
        )

        PracticalInfo.objects.create(
            residence=residence, order=1, title="Horaires du local à vélos",
            content="Accès libre de 6h à 22h avec le badge de résidence.",
        )
        PracticalInfo.objects.create(
            residence=residence, order=2, title="Tri sélectif",
            content="Collecte des ordures ménagères le mardi et le vendredi avant 8h.",
        )
        PracticalInfo.objects.create(
            residence=residence, order=3, title="Règlement intérieur",
            content="Les parties communes sont non-fumeurs. Merci de respecter le calme après 22h.",
        )

        WorkRecord.objects.create(
            residence=residence, title="Ravalement de façade", date=timezone.now().date() - timedelta(days=200),
            company="Façades & Co", amount=18500, description="Ravalement complet de la façade sur cour.",
        )
        WorkRecord.objects.create(
            residence=residence, title="Remplacement de la chaudière collective",
            date=timezone.now().date() - timedelta(days=60),
            company="Chauffage Services", amount=9200, description="Remplacement de la chaudière collective.",
        )
