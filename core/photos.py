"""Point d'entrée unique pour traiter une photo envoyée par un résident.

Utilisé par les 4 endroits qui créent une IncidentPhoto ou une PostPhoto
(incidents/views.py, wall/views.py). Aucune vue ne doit valider ou
ré-encoder une photo par ses propres moyens : tout passe par
`prepare_photo` / `prepare_photos`.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from .validators import MSG_NOT_AN_IMAGE, validate_photo

# Format Pillow (déterminé à l'ouverture du fichier) -> extension à utiliser
# pour le fichier ré-encodé. C'est cette extension, et non celle du fichier
# d'origine, qui doit être cohérente avec le nom finalement écrit sur disque
# par upload_to (incident_photo_upload / post_photo_upload), puisque ce sont
# elles qui lisent l'extension du nom de fichier transmis.
_SAVE_FORMAT = {
    "JPEG": ("JPEG", ".jpg"),
    "PNG": ("PNG", ".png"),
    "WEBP": ("WEBP", ".webp"),
}


def prepare_photo(f):
    """Valide une photo puis la ré-encode sans métadonnées EXIF/GPS.

    Retourne un `ContentFile` prêt pour `.objects.create(image=...)`. Le nom
    du fichier retourné porte l'extension du format réellement écrit (pas
    celle du fichier d'origine).

    Lève ValidationError (message en français) si la photo n'est pas valide.
    Pillow ne recopie pas les métadonnées EXIF lors d'un `Image.save()` sauf
    si on les lui fournit explicitement : le simple ré-encodage suffit donc
    à retirer les données GPS/EXIF.
    """
    validate_photo(f)

    f.seek(0)
    try:
        with Image.open(f) as img:
            pillow_format = img.format
            save_format, ext = _SAVE_FORMAT[pillow_format]

            # PNG/WebP peuvent avoir un canal alpha : ne jamais convertir en
            # RGB à l'aveugle sous peine de casser la transparence. JPEG ne
            # supporte pas l'alpha : conversion en RGB obligatoire (sans
            # risque, JPEG n'a jamais eu de transparence).
            has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                img.mode == "P" and "transparency" in img.info
            )

            if save_format == "JPEG":
                clean = img.convert("RGB")
            elif has_alpha:
                clean = img.convert("RGBA")
            else:
                clean = img.convert("RGB")

            # Ré-encodage entièrement en mémoire : aucun fichier
            # intermédiaire écrit sur disque, donc rien à nettoyer.
            buffer = BytesIO()
            save_kwargs = {"quality": 90} if save_format in ("JPEG", "WEBP") else {}
            clean.save(buffer, format=save_format, **save_kwargs)
    except (UnidentifiedImageError, OSError, KeyError):
        raise ValidationError(MSG_NOT_AN_IMAGE)

    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"photo{ext}")


def prepare_photos(files):
    """Valide et ré-encode une liste de fichiers uploadés.

    Comportement volontairement « tout ou rien » : dès qu'une photo du lot
    est invalide, une ValidationError est levée et AUCUNE photo du lot n'est
    retournée (les photos déjà traitées avant elle sont abandonnées). C'est
    à l'appelant d'englober la création de l'incident/du post dans une
    transaction (`transaction.atomic()`) pour que rien ne soit enregistré
    à moitié, et d'afficher le message d'erreur au résident.
    """
    return [prepare_photo(f) for f in files]
