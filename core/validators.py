import os

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

# Limites imposées aux photos envoyées par les résidents (incidents, mur).
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# Formats réellement reconnus par Pillow après ouverture du fichier
# (le contenu prime sur l'extension déclarée par le navigateur).
ALLOWED_PILLOW_FORMATS = {"JPEG", "PNG", "WEBP"}

MSG_TOO_LARGE = "Photo trop lourde (5 Mo maximum)."
MSG_BAD_FORMAT = "Format non accepté : JPG, PNG ou WebP uniquement."
MSG_NOT_AN_IMAGE = "Fichier invalide : ce n'est pas une image reconnue."


def validate_photo(f):
    """Valide une photo uploadée : taille, extension déclarée, contenu réel.

    Lève ValidationError avec un message en français, compréhensible par un
    résident non technique. Ne modifie pas le fichier (lecture seule) : le
    curseur est repositionné au début avant de rendre la main, pour que
    l'appelant puisse relire le fichier ensuite.
    """
    if f.size > MAX_UPLOAD_BYTES:
        raise ValidationError(MSG_TOO_LARGE)

    ext = os.path.splitext(f.name or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(MSG_BAD_FORMAT)

    f.seek(0)
    try:
        with Image.open(f) as img:
            img.verify()
            pillow_format = img.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError(MSG_NOT_AN_IMAGE)
    finally:
        f.seek(0)

    if pillow_format not in ALLOWED_PILLOW_FORMATS:
        # Cas typique : un PDF ou autre fichier renommé avec une extension
        # image (l'extension seule ne suffit jamais à faire confiance).
        raise ValidationError(MSG_BAD_FORMAT)
