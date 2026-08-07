from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from .forms import ContactForm, PracticalInfoForm, WorkRecordForm
from .models import Contact, PracticalInfo, WorkRecord

# kind d'URL -> (modèle, formulaire, libellé affiché)
KINDS = {
    "contact": (Contact, ContactForm, "un contact"),
    "info": (PracticalInfo, PracticalInfoForm, "une info pratique"),
    "travaux": (WorkRecord, WorkRecordForm, "des travaux"),
}


@login_required
def directory_home(request):
    rid = request.user.residence_id
    contacts = Contact.objects.filter(residence_id=rid)
    grouped = {}
    for c in contacts:
        grouped.setdefault(c.get_category_display(), []).append(c)
    works = WorkRecord.objects.filter(residence_id=rid)
    infos = PracticalInfo.objects.filter(residence_id=rid)
    return render(request, "directory/home.html", {"grouped": grouped, "works": works, "infos": infos})


def _kind_or_404(kind):
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


@login_required
def item_edit(request, kind, pk=None):
    """Création (sans pk) ou modification (avec pk) d'une fiche du carnet — conseil syndical uniquement."""
    model, form_cls, label = _kind_or_404(kind)
    if not request.user.is_council:
        return HttpResponseForbidden()
    instance = get_object_or_404(model, pk=pk, residence_id=request.user.residence_id) if pk else None
    form = form_cls(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.residence_id = request.user.residence_id
        obj.save()
        messages.success(request, "Fiche enregistrée")
        return redirect("directory_home")
    return render(request, "directory/form.html",
                  {"form": form, "label": label, "kind": kind, "instance": instance})


@login_required
def item_delete(request, kind, pk):
    model, _, _ = _kind_or_404(kind)
    if not request.user.is_council:
        return HttpResponseForbidden()
    obj = get_object_or_404(model, pk=pk, residence_id=request.user.residence_id)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Fiche supprimée")
    return redirect("directory_home")
