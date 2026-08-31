import os
import uuid

from django.conf import settings
from django.db import models
from core.models import Residence
from core.validators import validate_photo


def post_photo_upload(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"wall/{instance.post.residence_id}/{uuid.uuid4().hex}{ext}"


class Post(models.Model):
    TYPES = [
        ("alerte", "Alerte"),
        ("info", "Information"),
        ("evenement", "Événement"),
        ("entraide", "Entraide"),
    ]
    residence = models.ForeignKey(Residence, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="posts")
    type = models.CharField("Type", max_length=20, choices=TYPES, default="info")
    content = models.TextField("Message")
    event_date = models.DateField("Date de l'événement", null=True, blank=True)
    pinned = models.BooleanField("Épinglé", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} · {self.content[:40]}"

    TYPE_BADGES = {
        "alerte": "bg-red-100 text-red-800",
        "info": "bg-blue-100 text-blue-800",
        "evenement": "bg-purple-100 text-purple-800",
        "entraide": "bg-green-100 text-green-800",
    }

    @property
    def badge_class(self):
        return self.TYPE_BADGES[self.type]


class PostPhoto(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=post_photo_upload, validators=[validate_photo])


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Reaction(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("post", "user")
