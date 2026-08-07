"""Recherche globale. Requêtes ILIKE directes, bornées par résidence et modules actifs.
Pas de moteur d'indexation : volumétrie d'une copropriété = quelques centaines de lignes."""
from django.db.models import Q
from incidents.models import Incident
from wall.models import Post
from directory.models import Contact, PracticalInfo, WorkRecord


def search_all(user, query):
    """Retourne un dict {section: [résultats]}, uniquement pour les modules actifs de la résidence."""
    rid = user.residence_id
    from core.models import ResidenceModule
    active = set(ResidenceModule.objects.filter(residence_id=rid, enabled=True).values_list("module", flat=True))
    results = {}

    if "incidents" in active:
        results["incidents"] = list(
            Incident.objects.filter(residence_id=rid)
            .filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(location__icontains=query))
            .select_related("category")[:20]
        )

    if "wall" in active:
        results["posts"] = list(
            Post.objects.filter(residence_id=rid, content__icontains=query).select_related("author")[:20]
        )

    if "directory" in active:
        contacts = Contact.objects.filter(residence_id=rid).filter(
            Q(name__icontains=query) | Q(role__icontains=query) | Q(notes__icontains=query))
        infos = PracticalInfo.objects.filter(residence_id=rid).filter(
            Q(title__icontains=query) | Q(content__icontains=query))
        works = WorkRecord.objects.filter(residence_id=rid).filter(
            Q(title__icontains=query) | Q(company__icontains=query) | Q(description__icontains=query))
        directory = list(contacts[:10]) + list(infos[:10]) + list(works[:10])
        if directory:
            results["directory"] = directory

    return results
