from django.http import Http404
from .models import ResidenceModule

MODULE_PREFIXES = {"/incidents/": "incidents", "/mur/": "wall", "/carnet/": "directory"}


class ModuleGateMiddleware:
    """Bloque les URLs des modules désactivés pour la résidence de l'utilisateur."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.residence_id:
            for prefix, module in MODULE_PREFIXES.items():
                if request.path.startswith(prefix):
                    enabled = ResidenceModule.objects.filter(
                        residence_id=user.residence_id, module=module, enabled=True
                    ).exists()
                    if not enabled:
                        raise Http404
        return self.get_response(request)
