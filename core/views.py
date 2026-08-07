from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from .forms import JoinForm, ProfileForm
from .search import search_all


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


@login_required
def home(request):
    return redirect("incident_list")


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
