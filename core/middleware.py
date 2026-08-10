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

class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        r = self.get_response(request)
        r["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.tailwindcss.com https://unpkg.com 'unsafe-eval' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        r["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=(), usb=()"
        return r
