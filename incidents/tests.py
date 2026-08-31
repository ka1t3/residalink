import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

import pillow_heif
from core.models import Residence, User
from incidents.models import Incident, IncidentCategory, IncidentPhoto


def _jpeg_bytes(size=(500, 400), color=(120, 40, 200), quality=90):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _heic_bytes(size=(500, 400)):
    img = Image.new("RGB", size, (10, 90, 200))
    heif = pillow_heif.from_pillow(img)
    buf = io.BytesIO()
    heif.save(buf, format="HEIF")
    return buf.getvalue()


def _png_bytes():
    img = Image.new("RGBA", (100, 80), (10, 200, 30, 120))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _webp_bytes():
    img = Image.new("RGB", (120, 90), (200, 150, 10))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def _gps_jpeg_bytes():
    img = Image.new("RGB", (300, 200), (50, 50, 50))
    exif = Image.Exif()
    exif[0x0110] = "Caméra GPS Test"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (48.0, 51.0, 22.0)
    gps[3] = "E"
    gps[4] = (2.0, 20.0, 0.0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class IncidentPhotoPipelineTests(TestCase):
    """Les fichiers écrits par ces tests doivent atterrir dans un dossier
    temporaire, jamais dans media/ (les lignes en base sont annulées à la fin
    de chaque test, le signal post_delete ne se déclenche donc pas et les
    fichiers resteraient orphelins sur disque)."""

    def setUp(self):
        self._media_root = tempfile.mkdtemp(prefix="residalink-test-media-")
        self._media_override = override_settings(MEDIA_ROOT=self._media_root)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.addCleanup(shutil.rmtree, self._media_root, ignore_errors=True)
        self.residence = Residence.objects.create(name="Les Tilleuls")
        self.user = User.objects.create_user(
            username="photo@example.com", password="x",
            residence=self.residence, display_name="Photo",
        )
        self.category = IncidentCategory.objects.create(name="Fuite d'eau — test photo")
        self.client.force_login(self.user)

    def _post(self, photos, title="Titre"):
        return self.client.post(
            reverse("incident_new") + f"?cat={self.category.pk}",
            {"title": title, "description": "d", "location": "", "photos": photos},
            follow=True,
        )

    def test_jpeg_valide_cree_la_photo(self):
        resp = self._post(SimpleUploadedFile("photo.jpg", _jpeg_bytes(), content_type="image/jpeg"))
        incident = Incident.objects.get(title="Titre")
        self.assertEqual(incident.photos.count(), 1)
        self.assertTrue(incident.photos.first().image.name.endswith(".jpg"))
        self.assertNotContains(resp, "trop volumineuse")

    def test_png_et_webp_valides_cree_la_photo(self):
        self._post(SimpleUploadedFile("img.png", _png_bytes(), content_type="image/png"), title="PNG")
        self._post(SimpleUploadedFile("img.webp", _webp_bytes(), content_type="image/webp"), title="WEBP")
        self.assertEqual(Incident.objects.get(title="PNG").photos.count(), 1)
        self.assertEqual(Incident.objects.get(title="WEBP").photos.count(), 1)

    def test_heic_valide_stocke_en_jpeg_avec_extension_jpg(self):
        resp = self._post(SimpleUploadedFile("IMG_1234.HEIC", _heic_bytes(), content_type="image/heic"))
        incident = Incident.objects.get(title="Titre")
        self.assertEqual(incident.photos.count(), 1)
        photo = incident.photos.first()
        self.assertTrue(photo.image.name.endswith(".jpg"), photo.image.name)
        with Image.open(photo.image.path) as img:
            self.assertEqual(img.format, "JPEG")
        self.assertNotContains(resp, "reconnu")

    def test_photo_de_plus_de_5_mo_refusee_sans_objet_cree(self):
        grosse = SimpleUploadedFile("grosse.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * (8 * 1024 * 1024), content_type="image/jpeg")
        resp = self._post(grosse)
        self.assertContains(resp, "La photo grosse.jpg est trop volumineuse")
        self.assertContains(resp, "Taille maximale : 5 Mo")
        self.assertEqual(IncidentPhoto.objects.count(), 0)

    def test_contenu_non_image_refuse_proprement(self):
        resp = self._post(SimpleUploadedFile("fake.jpg", b"hello world", content_type="image/jpeg"))
        self.assertContains(resp, "pas pu être lue")
        self.assertEqual(IncidentPhoto.objects.count(), 0)

    def test_image_2000px_redimensionnee(self):
        self._post(SimpleUploadedFile("grande.jpg", _jpeg_bytes(size=(4000, 3000)), content_type="image/jpeg"))
        photo = IncidentPhoto.objects.get()
        with Image.open(photo.image.path) as img:
            self.assertLessEqual(max(img.size), 2000)
            self.assertEqual(img.size, (2000, 1500))

    def test_metadonnees_gps_supprimees(self):
        self._post(SimpleUploadedFile("gps.jpg", _gps_jpeg_bytes(), content_type="image/jpeg"))
        photo = IncidentPhoto.objects.get()
        with Image.open(photo.image.path) as img:
            exif = img.getexif()
            self.assertIsNone(exif.get(0x0110))
            self.assertEqual(exif.get_ifd(0x8825), {})

    def test_trois_photos_dont_une_invalide_deux_creees_un_message(self):
        resp = self._post([
            SimpleUploadedFile("ok1.jpg", _jpeg_bytes(), content_type="image/jpeg"),
            SimpleUploadedFile("bad.jpg", b"nope", content_type="image/jpeg"),
            SimpleUploadedFile("ok2.png", _png_bytes(), content_type="image/png"),
        ])
        incident = Incident.objects.get(title="Titre")
        self.assertEqual(incident.photos.count(), 2)
        self.assertContains(resp, "La photo bad.jpg")

    def test_edition_incident_ajoute_une_photo_valide(self):
        incident = Incident.objects.create(
            residence=self.residence, author=self.user, category=self.category, title="Existant",
        )
        self.client.post(
            reverse("incident_edit", args=[incident.pk]),
            {"title": "Existant", "description": "", "location": "",
             "photos": SimpleUploadedFile("ajout.jpg", _jpeg_bytes(), content_type="image/jpeg")},
            follow=True,
        )
        incident.refresh_from_db()
        self.assertEqual(incident.photos.count(), 1)

    def test_edition_incident_photo_invalide_refusee(self):
        incident = Incident.objects.create(
            residence=self.residence, author=self.user, category=self.category, title="Existant",
        )
        resp = self.client.post(
            reverse("incident_edit", args=[incident.pk]),
            {"title": "Existant", "description": "", "location": "",
             "photos": SimpleUploadedFile("bad.jpg", b"nope", content_type="image/jpeg")},
            follow=True,
        )
        incident.refresh_from_db()
        self.assertEqual(incident.photos.count(), 0)
        self.assertContains(resp, "La photo bad.jpg")

    def test_edition_incident_limite_deja_atteinte_aucune_photo_ajoutee(self):
        """Incident déjà à 3 photos : l'envoi d'une nouvelle photo n'en crée
        aucune et un message d'erreur explicite est affiché — pas un succès
        silencieux qui laisserait croire à l'ajout."""
        incident = Incident.objects.create(
            residence=self.residence, author=self.user, category=self.category, title="Existant",
        )
        for i in range(3):
            incident.photos.create(image=SimpleUploadedFile(f"p{i}.jpg", _jpeg_bytes(), content_type="image/jpeg"))
        resp = self.client.post(
            reverse("incident_edit", args=[incident.pk]),
            {"title": "Existant", "description": "", "location": "",
             "photos": SimpleUploadedFile("nouvelle.jpg", _jpeg_bytes(), content_type="image/jpeg")},
            follow=True,
        )
        incident.refresh_from_db()
        self.assertEqual(incident.photos.count(), 3)
        self.assertContains(resp, "Vous avez déjà 3 photos")

    def test_edition_incident_limite_atteinte_en_cours_envoi(self):
        """2 photos existantes + 3 envoyées : seule 1 est enregistrable, les
        2 écartées sont nommées dans le message."""
        incident = Incident.objects.create(
            residence=self.residence, author=self.user, category=self.category, title="Existant",
        )
        for i in range(2):
            incident.photos.create(image=SimpleUploadedFile(f"p{i}.jpg", _jpeg_bytes(), content_type="image/jpeg"))
        resp = self.client.post(
            reverse("incident_edit", args=[incident.pk]),
            {"title": "Existant", "description": "", "location": "",
             "photos": [
                 SimpleUploadedFile("nouvelle1.jpg", _jpeg_bytes(), content_type="image/jpeg"),
                 SimpleUploadedFile("nouvelle2.jpg", _jpeg_bytes(), content_type="image/jpeg"),
                 SimpleUploadedFile("nouvelle3.jpg", _jpeg_bytes(), content_type="image/jpeg"),
             ]},
            follow=True,
        )
        incident.refresh_from_db()
        self.assertEqual(incident.photos.count(), 3)
        self.assertContains(resp, "Limite de 3 photos atteinte")
        self.assertContains(resp, "nouvelle2.jpg")
        self.assertContains(resp, "nouvelle3.jpg")
