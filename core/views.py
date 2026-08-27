import os
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import JoinForm, ProfileForm
from .models import PublicRequestCooldown, User
from .search import search_all


def service_worker(request):
    with open(os.path.join(settings.BASE_DIR, "static", "sw.js")) as f:
        resp = HttpResponse(f.read(), content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    return resp


def favicon(request):
    with open(os.path.join(settings.BASE_DIR, "static", "favicon.ico"), "rb") as f:
        return HttpResponse(f.read(), content_type="image/x-icon")


def join(request):
    if request.user.is_authenticated:
        if request.user.is_demo:
            # Un visiteur en session démo n'a pas de « vrai » compte à
            # protéger : on le déconnecte pour lui laisser rejoindre sa
            # résidence avec un code, plutôt que de le renvoyer dans la démo.
            logout(request)
            messages.info(request, "Vous avez quitté la démonstration.")
        else:
            return redirect("home")
    form = JoinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            premier = not User.objects.filter(residence=form.residence).exists()
            user = form.save()
            if premier:
                Group.objects.get_or_create(name="conseil_syndical")[0].user_set.add(user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Bienvenue dans la résidence {user.residence.name} !")
        return redirect("home")
    return render(request, "core/join.html", {"form": form})


def _dashboard_redirect(user):
    """Redirige vers le premier module activé de la résidence de `user`."""
    from .models import ResidenceModule
    mods = set(ResidenceModule.objects.filter(
        residence_id=user.residence_id, enabled=True
    ).values_list("module", flat=True))
    if "wall" in mods: return redirect("post_list")
    if "incidents" in mods: return redirect("incident_list")
    if "directory" in mods: return redirect("directory_home")
    return redirect("profile")


def demo(request):
    """Connecte le visiteur au compte de démonstration (lecture seule).

    - Un utilisateur déjà connecté et non-démo n'est jamais déconnecté.
    - Si la résidence de démonstration n'existe pas (pas encore de
      `reset_demo`), on redirige sans planter.
    """
    if request.user.is_authenticated:
        if not request.user.is_demo:
            messages.info(
                request,
                "Vous êtes déjà connecté à votre compte : impossible de "
                "basculer sur la démonstration sans vous déconnecter.",
            )
            return redirect("home")
        return _dashboard_redirect(request.user)

    demo_user = User.objects.filter(is_demo=True, residence__is_demo=True).select_related("residence").first()
    if demo_user is None:
        messages.error(request, "La démonstration n'est pas disponible pour le moment.")
        return redirect("home")

    login(request, demo_user, backend="django.contrib.auth.backends.ModelBackend")
    return _dashboard_redirect(demo_user)


def home(request):
    # `creer` : lien "Créer ma résidence" du bandeau démo, avec ancre #creer.
    # `accueil` : bouton "Retour à l'accueil", pour qu'un visiteur en session
    # démo puisse revoir la landing page sans quitter sa session démo.
    if (
        not request.user.is_authenticated
        or request.GET.get("creer")
        or request.GET.get("accueil")
    ):
        return render(request, "landing.html", {"ts": _contact_ts()})
    return _dashboard_redirect(request.user)


def _client_ip(request):
    """IP du client derrière le proxy (premier hôte de X-Forwarded-For)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _endpoint_allowed(key, request, seconds=3600):
    """Retourne True si l'IP n'a PAS dépassé la limite pour cet endpoint.

    Enregistre le passage et purge au passage les entrées obsolètes.
    """
    ip = _client_ip(request)
    now = timezone.now()
    entry = PublicRequestCooldown.objects.filter(key=key, ip=ip).first()
    if entry and now - entry.last_at < timedelta(seconds=seconds):
        return False
    PublicRequestCooldown.objects.update_or_create(key=key, ip=ip, defaults={"last_at": now})
    PublicRequestCooldown.objects.filter(last_at__lt=now - timedelta(seconds=seconds)).delete()
    return True


def residence_request(request):
    """Formulaire public de création de résidence.

    En mode résidence unique (OPEN_REGISTRATION=False) : la route n'existe pas
    (404, sans jamais confirmer son existence), quelle que soit la méthode.

    Anti-spam : honeypot + délai minimal signé (comme /contact/) +
    limitation 1 demande / IP / heure (stockée en base).
    Un bot est accepté silencieusement (aucune erreur confirmée).
    """
    if not settings.OPEN_REGISTRATION:
        raise Http404
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    address = request.POST.get("address", "").strip()
    role = request.POST.get("role", "").strip()
    message = request.POST.get("message", "").strip()
    silent_ok = redirect(f"{reverse('home')}?envoye=1#creer")

    # 1. Honeypot : un bot qui remplit ce champ est accepté sans e-mail.
    if request.POST.get("website", "").strip():
        return silent_ok

    # 2. Délai minimal signé : le formulaire doit avoir été affiché ≥ 3 s.
    try:
        ts = int(signing.TimestampSigner().unsign(request.POST.get("ts", "")))
    except (signing.BadSignature, ValueError, TypeError):
        ts = None
    if ts is None or int(time.time()) - ts < 3:
        return silent_ok

    if not (name and email and address):
        return redirect(f"{reverse('home')}?erreur=1#creer")

    # 3. Limitation de débit par IP : 1 demande / heure.
    if not _endpoint_allowed("residence_request", request, seconds=3600):
        return silent_ok

    corps = (
        "Nouvelle demande de création de résidence\n\n"
        f"Nom : {name}\n"
        f"E-mail : {email}\n"
        f"Adresse : {address}\n"
        f"Profil : {role or '—'}\n"
        f"Message : {message or '—'}\n"
    )
    EmailMessage(
        subject=f"[Residalink] Demande de résidence — {name}",
        body=corps,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[getattr(settings, "SIGNUP_NOTIFY_EMAIL", settings.DEFAULT_FROM_EMAIL)],
        reply_to=[email],
    ).send(fail_silently=False)

    return silent_ok


def _contact_ts():
    return signing.TimestampSigner().sign(str(int(time.time())))


def contact(request):
    """Formulaire de contact public. Aucun stockage en base : le message est
    envoyé par e-mail puis oublié. Anti-spam : honeypot + délai minimal de
    3 secondes (horodatage signé)."""
    nom = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    message = request.POST.get("message", "").strip()
    erreurs = []

    if request.method == "POST":
        if not request.POST.get("website", "").strip():
            try:
                ts = int(signing.TimestampSigner().unsign(request.POST.get("ts", "")))
            except (signing.BadSignature, ValueError, TypeError):
                ts = None
            if ts is not None and int(time.time()) - ts >= 3:
                if not nom:
                    erreurs.append("Le nom est obligatoire.")
                if not email:
                    erreurs.append("L'e-mail est obligatoire.")
                else:
                    try:
                        validate_email(email)
                    except ValidationError:
                        erreurs.append("Cette adresse e-mail n'est pas valide.")
                if not message:
                    erreurs.append("Le message est obligatoire.")
                if not erreurs:
                    corps = (
                        "Nouveau message de contact\n\n"
                        f"Nom : {nom}\n"
                        f"E-mail : {email}\n"
                        f"Message : {message}\n"
                    )
                    try:
                        EmailMessage(
                            subject=f"[Residalink] Message de contact — {nom}",
                            body=corps,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            to=[getattr(settings, "SIGNUP_NOTIFY_EMAIL", settings.DEFAULT_FROM_EMAIL)],
                            reply_to=[email],
                        ).send(fail_silently=False)
                    except Exception:
                        erreurs.append("L'envoi du message a échoué. Merci de réessayer dans quelques instants.")
                    else:
                        messages.success(request, "Message envoyé, merci ! Nous vous répondrons rapidement.")
                        return redirect("contact")
        if not erreurs:
            return redirect("contact")

    return render(request, "core/contact.html", {
        "nom": nom,
        "email": email,
        "message": message,
        "erreurs": erreurs,
        "ts": _contact_ts(),
    })


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil enregistré")
        return redirect("profile")
    return render(request, "core/profile.html", {"form": form})


@login_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)  # reste connecté après le changement
        messages.success(request, "Mot de passe modifié")
        return redirect("profile")
    return render(request, "core/password_change.html", {"form": form})


@login_required
def search(request):
    query = request.GET.get("q", "").strip()
    results = search_all(request.user, query) if query else {}
    total = sum(len(v) for v in results.values())
    return render(request, "core/search.html", {"query": query, "results": results, "total": total})


def _residence_members(request):
    """Utilisateurs de LA résidence de request.user — jamais d'une autre résidence."""
    if not request.user.residence_id:
        raise Http404()
    return User.objects.filter(residence_id=request.user.residence_id)


@login_required
def members_list(request):
    if not request.user.is_council:
        raise Http404()
    council_group, _ = Group.objects.get_or_create(name="conseil_syndical")
    members = _residence_members(request).order_by("display_name", "username")
    council_ids = set(members.filter(groups=council_group).values_list("id", flat=True))
    return render(request, "core/members_list.html", {
        "members": members,
        "council_ids": council_ids,
    })


@login_required
@require_POST
def member_toggle_council(request, pk):
    if not request.user.is_council:
        raise Http404()
    residence_members = _residence_members(request)
    member = get_object_or_404(residence_members, pk=pk)
    council_group, _ = Group.objects.get_or_create(name="conseil_syndical")

    with transaction.atomic():
        is_member = member.groups.filter(pk=council_group.pk).exists()
        if is_member:
            council_count = residence_members.filter(groups=council_group).count()
            if council_count <= 1:
                messages.error(
                    request,
                    "Impossible de retirer le dernier membre du conseil syndical de la résidence.",
                )
                return redirect("members_list")
            council_group.user_set.remove(member)
            messages.success(request, f"{member.public_name} a été retiré du conseil syndical.")
        else:
            council_group.user_set.add(member)
            messages.success(request, f"{member.public_name} a été nommé au conseil syndical.")
    return redirect("members_list")
