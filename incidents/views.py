from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from core.emails import notify
from core.models import User
from core.photos import save_photos
from .models import Incident, IncidentCategory, IncidentFollower, IncidentPhoto, IncidentUpdate


def _residence_incidents(request):
    return Incident.objects.filter(residence_id=request.user.residence_id).select_related("category")


def _council_members(residence_id):
    return User.objects.filter(residence_id=residence_id, groups__name="conseil_syndical")


def _watchers(incident):
    """Auteur + suiveurs, sans l'utilisateur courant."""
    users = {incident.author} | {f.user for f in incident.followers.select_related("user")}
    users.discard(None)
    return users


@login_required
def incident_list(request):
    incidents = _residence_incidents(request).prefetch_related("followers")
    status = request.GET.get("statut", "")
    cat = request.GET.get("categorie", "")
    if status:
        incidents = incidents.filter(status=status)
    if cat:
        incidents = incidents.filter(category_id=cat)
    incidents = list(incidents)
    open_incidents = [i for i in incidents if i.is_open]
    resolved = [i for i in incidents if not i.is_open][:10]
    return render(request, "incidents/list.html", {
        "open_incidents": open_incidents, "resolved": resolved,
        "statuses": Incident.STATUSES, "categories": IncidentCategory.objects.all(),
        "active_status": status, "active_cat": cat,
    })


@login_required
def incident_new(request):
    """Étape 1 : catégorie. Étape 2 : anti-doublon + formulaire."""
    cat_id = request.GET.get("cat")
    if not cat_id:
        return render(request, "incidents/new_category.html", {"categories": IncidentCategory.objects.all()})

    category = get_object_or_404(IncidentCategory, pk=cat_id)
    duplicates = _residence_incidents(request).filter(category=category).exclude(status="resolu")

    if request.method == "POST":
        incident = Incident.objects.create(
            residence_id=request.user.residence_id,
            author=request.user,
            category=category,
            title=request.POST.get("title", "").strip()[:120] or category.name,
            description=request.POST.get("description", "").strip(),
            location=request.POST.get("location", "").strip(),
        )
        _, photo_errors = save_photos(incident, request.FILES.getlist("photos"))
        for error in photo_errors:
            messages.error(request, error)
        IncidentUpdate.objects.create(incident=incident, author=request.user, new_status="signale")
        notify(_council_members(request.user.residence_id),
               f"[{request.user.residence.name}] Nouvel incident : {incident.title}",
               f"{request.user.public_name} a signalé un incident ({category.name}).\n\n{incident.description}",
               f"/incidents/{incident.pk}/", kind="incidents")
        messages.success(request, "Incident signalé. Le conseil syndical est prévenu.")
        return redirect("incident_detail", pk=incident.pk)

    return render(request, "incidents/new_form.html",
                  {"category": category, "duplicates": duplicates})


@login_required
def incident_detail(request, pk):
    incident = get_object_or_404(_residence_incidents(request), pk=pk)
    is_follower = incident.followers.filter(user=request.user).exists()
    return render(request, "incidents/detail.html",
                  {"incident": incident, "is_follower": is_follower, "statuses": Incident.STATUSES})


@login_required
def incident_follow(request, pk):
    incident = get_object_or_404(_residence_incidents(request), pk=pk)
    IncidentFollower.objects.get_or_create(incident=incident, user=request.user)
    messages.success(request, "Vous serez informé de l'avancement de cet incident.")
    return redirect("incident_detail", pk=pk)


@login_required
def incident_update(request, pk):
    """Ajout d'un commentaire (tous) ou changement de statut (conseil syndical)."""
    incident = get_object_or_404(_residence_incidents(request), pk=pk)
    if request.method != "POST":
        return redirect("incident_detail", pk=pk)

    new_status = request.POST.get("status", "")
    message = request.POST.get("message", "").strip()

    if new_status and new_status != incident.status:
        if not request.user.is_council:
            return HttpResponseForbidden()
        old = incident.status
        incident.status = new_status
        incident.resolved_at = timezone.now() if new_status == "resolu" else None
        incident.save()
        IncidentUpdate.objects.create(incident=incident, author=request.user,
                                      old_status=old, new_status=new_status, message=message)
        notify(_watchers(incident) - {request.user},
               f"[{incident.residence.name}] {incident.title} : {incident.get_status_display()}",
               f"{request.user.display_name} (conseil syndical) a mis à jour l'incident.\n\n{message}",
               f"/incidents/{incident.pk}/", kind="incidents")
    elif message:
        IncidentUpdate.objects.create(incident=incident, author=request.user, message=message)
        notify(_watchers(incident) - {request.user},
               f"[{incident.residence.name}] Nouveau message sur : {incident.title}",
               f"{request.user.public_name} : {message}",
               f"/incidents/{incident.pk}/", kind="incidents")
    return redirect("incident_detail", pk=pk)

@login_required
def incident_edit(request, pk):
    incident = get_object_or_404(_residence_incidents(request), pk=pk, author=request.user)
    if request.method == "POST":
        incident.title = request.POST.get("title", "").strip()[:120] or incident.title
        incident.description = request.POST.get("description", "").strip()
        incident.location = request.POST.get("location", "").strip()
        cat_id = request.POST.get("category")
        if cat_id:
            incident.category = get_object_or_404(IncidentCategory, pk=cat_id)
        incident.save()
        for photo in IncidentPhoto.objects.filter(
                pk__in=request.POST.getlist("delete_photos"), incident=incident):
            photo.delete()
        remaining = 3 - incident.photos.count()
        _, photo_errors = save_photos(incident, request.FILES.getlist("photos"), limit=remaining)
        for error in photo_errors:
            messages.error(request, error)
        messages.success(request, "Incident modifié")
        return redirect("incident_detail", pk=incident.pk)
    return render(request, "incidents/edit.html",
                  {"incident": incident, "categories": IncidentCategory.objects.all()})