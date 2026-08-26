from django.conf import settings

from .models import ResidenceModule


def active_modules(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.residence_id):
        return {"active_modules": []}
    mods = ResidenceModule.objects.filter(residence_id=user.residence_id, enabled=True).values_list("module", flat=True)
    return {"active_modules": list(mods)}


def donate_url(request):
    return {"donate_url": settings.DONATE_URL}
