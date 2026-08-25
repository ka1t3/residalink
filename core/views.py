import os
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import JoinForm, ProfileForm
from .search import search_all


def service_worker(request):
    with open(os.path.join(settings.BASE_DIR, "static", "sw.js")) as f:
        resp = HttpResponse(f.read(), content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    return resp


def join(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = JoinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Bienvenue dans la résidence {user.residence.name} !")
        return redirect("home")
    return render(request, "core/join.html", {"form": form})


def home(request):
    if not request.user.is_authenticated:
        return render(request, "landing.html")
    from .models import ResidenceModule
    mods = set(ResidenceModule.objects.filter(
        residence_id=request.user.residence_id, enabled=True
    ).values_list("module", flat=True))
    if "wall" in mods: return redirect("post_list")
    if "incidents" in mods: return redirect("incident_list")
    if "directory" in mods: return redirect("directory_home")
    return redirect("profile")


@require_POST
def residence_request(request):
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    address = request.POST.get("address", "").strip()
    role = request.POST.get("role", "").strip()
    message = request.POST.get("message", "").strip()

    if not (name and email and address):
        return redirect(f"{reverse('home')}?erreur=1#creer")

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

    return redirect(f"{reverse('home')}?envoye=1#creer")


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
