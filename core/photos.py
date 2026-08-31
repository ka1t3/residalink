"""Point d'entrée unique pour traiter une photo envoyée par un résident.

Utilisé par les 4 endroits qui créent une IncidentPhoto ou une PostPhoto
(incidents/views.py, wall/views.py) via `save_photos`. Aucune vue ne doit
valider ou ré-encoder une photo par ses propres moyens : tout passe par
`prepare_photo` / `save_photos`.
"""

import logging
import os
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .validators import MSG_NOT_AN_IMAGE, validate_photo

logger = logging.getLogger(__name__)

# Nombre maximal de photos qu'un incident ou un post peut avoir. Seule
# constante à changer si la limite devait un jour évoluer (message d'erreur
# ci-dessous + core/photos.py::save_photos + incidents/views.py +
# wall/views.py, qui l'importent tous d'ici).
PHOTO_LIMIT = 3

# Limite Pillow au nombre de pixels décodés en mémoire (largeur × hauteur),
# **globale au processus** (pas seulement à ce module). `Image.open()`
# décompresse l'image entière avant tout traitement : sans cette limite, une
# image très compressée peut décompresser vers plusieurs dizaines de
# mégapixels — plusieurs centaines de Mo de RAM — et déclencher l'OOM killer
# sur un conteneur de production à ressources limitées, surtout avec
# plusieurs envois simultanés. 50_000_000 px reste largement supérieur à ce
# qu'exige MAX_DIMENSION=2000 (2000×2000 = 4_000_000 px maximum après
# redimensionnement, mais l'image *source*, avant redimensionnement, peut
# être bien plus grande) : au-delà de 2×cette limite, Pillow lève
# `Image.DecompressionBombError`, déjà capturé dans `validate_photo` et
# `prepare_photo` et converti en message français. Affecté ici, au premier
# import de ce module (donc avant tout traitement de photo), pour ne pas
# entrer en conflit avec la valeur que `pillow_heif` pourrait lire/écrire de
# son côté.
Image.MAX_IMAGE_PIXELS = 50_000_000

# Format Pillow (déterminé à l'ouverture du fichier) -> (format de sortie,
# extension du fichier ré-encodé). C'est cette extension, et non celle du
# fichier d'origine, qui doit être cohérente avec le nom finalement écrit sur
# disque par upload_to (incident_photo_upload / post_photo_upload).
#
# HEIF (HEIC/HEIF des téléphones) n'est décodable par aucun navigateur : il
# est systématiquement converti en JPEG à l'enregistrement. Le nom de fichier
# transmis porte alors l'extension .jpg, pas .heic — l'upload_to reprend
# l'extension du nom transmis.
_SAVE_FORMAT = {
    "JPEG": ("JPEG", ".jpg"),
    "PNG": ("PNG", ".png"),
    "WEBP": ("WEBP", ".webp"),
    "HEIF": ("JPEG", ".jpg"),
}

# Plus grand côté maximal d'une photo stockée (côté serveur, sans JS).
MAX_DIMENSION = 2000


def _name(f):
    return os.path.basename(f.name or "")


def prepare_photo(f):
    """Valide une photo puis la ré-encode sans métadonnées EXIF/GPS.

    - HEIC/HEIF → JPEG (aucun navigateur ne décode le HEIC) ;
    - plus grand côté réduit à `MAX_DIMENSION` si dépassement (ratio
      conservé) ;
    - orientation EXIF appliquée, puis métadonnées EXIF/GPS supprimées.

    Retourne un `ContentFile` prêt pour `.objects.create(image=...)`. Le nom
    du fichier retourné porte l'extension du format réellement écrit (pas
    celle du fichier d'origine) : un HEIC devient `photo.jpg`.

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

            # Orientation EXIF : appliquée aux pixels AVANT suppression des
            # métadonnées, sinon les photos prises en portrait seraient
            # stockées à l'envers. `exif_transpose` retourne une copie dès
            # qu'une orientation est présente.
            img = ImageOps.exif_transpose(img)

            # Redimensionnement côté serveur : plus grand côté ramené à
            # MAX_DIMENSION si dépassement, ratio conservé.
            if max(img.size) > MAX_DIMENSION:
                img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

            # PNG/WebP/HEIF peuvent avoir un canal alpha : ne jamais convertir
            # en RGB à l'aveugle sous peine de casser la transparence. JPEG ne
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
    except (UnidentifiedImageError, OSError, KeyError, ValueError, Image.DecompressionBombError):
        # KeyError peut signaler un vrai bug interne (ex. format absent de
        # _SAVE_FORMAT) plutôt qu'une photo réellement invalide : sans trace,
        # ce serait indistinguable côté logs d'un simple refus utilisateur.
        logger.warning("prepare_photo failed for %r", getattr(f, "name", None), exc_info=True)
        raise ValidationError(MSG_NOT_AN_IMAGE.format(name=_name(f)))

    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"photo{ext}")


def save_photos(instance, files, limit=PHOTO_LIMIT):
    """Valide, traite et enregistre les photos d'un incident ou d'un post.

    Comportement « meilleur effort » : chaque fichier est traité
    indépendamment. Une photo invalide est refusée avec un message d'erreur,
    mais ne fait pas échouer les autres — un résident qui envoie 3 photos
    dont 1 invalide garde les 2 valides et voit laquelle a été refusée.

    - `instance` : Incident ou Post (doit avoir un manager lié `photos`).
    - `files` : itérable d'UploadedFile.
    - `limit` : nombre de photos qu'il est encore possible d'enregistrer
      (les appelants passent `PHOTO_LIMIT - photos.count()` lors d'une
      modification).

    Retourne (created, erreurs) : nombre de photos créées et liste des
    messages d'erreur en français. Aucun fichier fourni n'est jamais
    enregistré silencieusement : si `limit` est déjà atteint, ou l'est en
    cours de traitement, un message d'erreur explicite est ajouté à
    `erreurs` (nommant, le cas échéant, les fichiers écartés).
    """
    files = list(files)
    created = 0
    erreurs = []

    if not files:
        return created, erreurs

    if limit <= 0:
        erreurs.append(
            f"Vous avez déjà {PHOTO_LIMIT} photos. Supprimez-en une avant d'en ajouter une nouvelle."
        )
        return created, erreurs

    discarded = []
    for f in files:
        if created >= limit:
            discarded.append(_name(f) or "photo")
            continue
        try:
            content = prepare_photo(f)
        except ValidationError as e:
            erreurs.extend(e.messages)
            continue
        instance.photos.create(image=content)
        created += 1

    if discarded:
        noms = ", ".join(discarded)
        if len(discarded) == 1:
            erreurs.append(f"Limite de {PHOTO_LIMIT} photos atteinte : « {noms} » n'a pas été ajoutée.")
        else:
            erreurs.append(f"Limite de {PHOTO_LIMIT} photos atteinte : {noms} n'ont pas été ajoutées.")

    return created, erreurs
