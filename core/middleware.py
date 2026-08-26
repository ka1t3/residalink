from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import ResidenceModule

MODULE_PREFIXES = {"/incidents/": "incidents", "/mur/": "wall", "/carnet/": "directory"}

SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")

# Routes dont le POST est autorisé en session démo, par nom de route.
# Tout nouveau formulaire public doit être ajouté ici, sinon il est bloqué
# silencieusement pour un visiteur en session démo.
# `login` est inclus : un visiteur en démo qui choisit de se connecter avec un
# vrai compte doit pouvoir soumettre le formulaire. Ce n'est pas une brèche du
# mode lecture seule : `django.contrib.auth.login()` détecte que l'identifiant
# en session diffère du nouvel utilisateur et purge la session (`session.flush()`)
# avant d'authentifier le nouveau compte — la session démo ne survit jamais à
# une connexion réussie.
DEMO_ALLOWED_ROUTE_NAMES = {"logout", "login", "residence_request", "contact"}


class DemoReadOnlyMiddleware:
    """Passe en lecture seule tout compte de démonstration (`user.is_demo`).

    Bloque toute requête de méthode non sûre (POST/PUT/PATCH/DELETE) — sauf la
    déconnexion — sans jamais modifier les vues existantes : la sécurité tient
    entièrement dans ce middleware, pas dans un patch des vues.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # AnonymousUser n'a pas d'attribut `is_demo` : getattr avec défaut
        # évite un crash pour tout visiteur non connecté.
        if request.method not in SAFE_METHODS and getattr(request.user, "is_demo", False):
            # On identifie la vue de déconnexion par son nom de route (résolu
            # depuis le chemin), jamais par une comparaison de chemin en dur :
            # une route renommée ou déplacée ne casserait pas silencieusement
            # l'exception.
            try:
                url_name = resolve(request.path).url_name
            except Resolver404:
                url_name = None
            if url_name not in DEMO_ALLOWED_ROUTE_NAMES:
                messages.warning(
                    request,
                    "Mode démonstration : les modifications sont désactivées.",
                )
                return redirect(self._safe_referer(request))
        return self.get_response(request)

    @staticmethod
    def _safe_referer(request):
        referer = request.META.get("HTTP_REFERER")
        # HTTP_REFERER est fourni par le client : ne jamais y rediriger sans
        # validation, sous peine d'open redirect.
        if referer and url_has_allowed_host_and_scheme(
            referer,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return referer
        return reverse("home")


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
