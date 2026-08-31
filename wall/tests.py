import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

import pillow_heif
from core.models import Residence, User
from wall.models import Post, PostPhoto


def _jpeg_bytes():
    img = Image.new("RGB", (500, 400), (120, 40, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _heic_bytes():
    img = Image.new("RGB", (500, 400), (10, 90, 200))
    heif = pillow_heif.from_pillow(img)
    buf = io.BytesIO()
    heif.save(buf, format="HEIF")
    return buf.getvalue()


class PostPhotoPipelineTests(TestCase):

    def setUp(self):
        self.residence = Residence.objects.create(name="Les Tilleuls")
        self.user = User.objects.create_user(
            username="photo-wall@example.com", password="x",
            residence=self.residence, display_name="Photo",
        )
        self.client.force_login(self.user)

    def test_creation_post_avec_photo_jpeg(self):
        resp = self.client.post(
            reverse("post_create"),
            {"content": "Message avec photo", "type": "info",
             "photos": SimpleUploadedFile("photo.jpg", _jpeg_bytes(), content_type="image/jpeg")},
            follow=True,
        )
        post = Post.objects.get(content="Message avec photo")
        self.assertEqual(post.photos.count(), 1)
        self.assertTrue(post.photos.first().image.name.endswith(".jpg"))
        self.assertNotContains(resp, "trop volumineuse")

    def test_creation_post_avec_photo_heic_stockee_en_jpg(self):
        self.client.post(
            reverse("post_create"),
            {"content": "HEIC", "type": "info",
             "photos": SimpleUploadedFile("IMG.HEIC", _heic_bytes(), content_type="image/heic")},
            follow=True,
        )
        post = Post.objects.get(content="HEIC")
        self.assertEqual(post.photos.count(), 1)
        photo = post.photos.first()
        self.assertTrue(photo.image.name.endswith(".jpg"), photo.image.name)
        with Image.open(photo.image.path) as img:
            self.assertEqual(img.format, "JPEG")

    def test_creation_post_photo_invalide_refusee(self):
        resp = self.client.post(
            reverse("post_create"),
            {"content": "Invalide", "type": "info",
             "photos": SimpleUploadedFile("bad.jpg", b"nope", content_type="image/jpeg")},
            follow=True,
        )
        post = Post.objects.get(content="Invalide")
        self.assertEqual(post.photos.count(), 0)
        self.assertContains(resp, "La photo bad.jpg")

    def test_edition_post_ajoute_une_photo_valide(self):
        post = Post.objects.create(
            residence=self.residence, author=self.user, type="info", content="Existant",
        )
        self.client.post(
            reverse("post_edit", args=[post.pk]),
            {"content": "Existant", "type": "info",
             "photos": SimpleUploadedFile("ajout.jpg", _jpeg_bytes(), content_type="image/jpeg")},
            follow=True,
        )
        post.refresh_from_db()
        self.assertEqual(post.photos.count(), 1)

    def test_edition_post_photo_invalide_refusee(self):
        post = Post.objects.create(
            residence=self.residence, author=self.user, type="info", content="Existant",
        )
        resp = self.client.post(
            reverse("post_edit", args=[post.pk]),
            {"content": "Existant", "type": "info",
             "photos": SimpleUploadedFile("bad.jpg", b"nope", content_type="image/jpeg")},
            follow=True,
        )
        post.refresh_from_db()
        self.assertEqual(post.photos.count(), 0)
        self.assertContains(resp, "La photo bad.jpg")

    def test_suppression_photo_objets_un_par_un(self):
        post = Post.objects.create(
            residence=self.residence, author=self.user, type="info", content="Existant",
        )
        for name in ("a.jpg", "b.jpg"):
            PostPhoto.objects.create(post=post, image=SimpleUploadedFile(name, _jpeg_bytes(), content_type="image/jpeg"))
        self.assertEqual(post.photos.count(), 2)
        self.client.post(
            reverse("post_edit", args=[post.pk]),
            {"content": "Existant", "type": "info", "delete_photos": [str(post.photos.first().pk)]},
            follow=True,
        )
        post.refresh_from_db()
        self.assertEqual(post.photos.count(), 1)
