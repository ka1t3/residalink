import logging
import os

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

# Limites imposées aux photos envoyées par les résidents (incidents, mur).
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
# Formats réellement reconnus par Pillow après ouverture du fichier
# (le contenu prime sur l'extension déclarée par le navigateur).
# "HEIF" est le format renvoyé par Pillow pour un HEIC/HEIF via pillow-heif.
ALLOWED_PILLOW_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}

MSG_TOO_LARGE = "La photo {name} est trop volumineuse ({size} Mo). Taille maximale : 5 Mo."
MSG_BAD_FORMAT = "Le format de la photo {name} n'est pas reconnu. Formats acceptés : JPG, PNG, WEBP, HEIC."
MSG_NOT_AN_IMAGE = "La photo {name} n'a pas pu être lue. Essayez avec une autre photo."


def _size_in_mo(size):
    return max(1, round(size / (1024 * 1024)))


def validate_photo(f):
    """Valide une photo uploadée : taille, extension déclarée, contenu réel.

    Lève ValidationError avec un message en français, compréhensible par un
    résident non technique. Ne modifie pas le fichier (lecture seule) : le
    curseur est repositionné au début avant de rendre la main, pour que
    l'appelant puisse relire le fichier ensuite.
    """
    name = os.path.basename(f.name or "")

    if f.size > MAX_UPLOAD_BYTES:
        raise ValidationError(MSG_TOO_LARGE.format(name=name, size=_size_in_mo(f.size)))

    ext = os.path.splitext(f.name or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(MSG_BAD_FORMAT.format(name=name))

    f.seek(0)
    try:
        with Image.open(f) as img:
            img.verify()
            pillow_format = img.format
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        # Un ValueError peut aussi trahir un bug interne plutôt qu'une photo
        # invalide : on garde une trace serveur avant de convertir en message
        # utilisateur générique.
        logger.warning("validate_photo failed for %r", name, exc_info=True)
        raise ValidationError(MSG_NOT_AN_IMAGE.format(name=name))
    finally:
        f.seek(0)

    if pillow_format not in ALLOWED_PILLOW_FORMATS:
        # Cas typique : un PDF ou autre fichier renommé avec une extension
        # image (l'extension seule ne suffit jamais à faire confiance).
        raise ValidationError(MSG_BAD_FORMAT.format(name=name))
