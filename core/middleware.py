from django.contrib import messages
from django.contrib.auth import logout
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

# Périmètre de navigation autorisé pour un utilisateur `is_demo`, par nom de
# route (jamais par comparaison de chaînes d'URL : les noms de routes sont
# stables, les chemins ne doivent pas servir d'ancrage).
#
# ⚠️ Piège coûteux : toute nouvelle page est HORS périmètre par défaut et
# ferme la session démo. Si elle fait partie du tour de démonstration, son
# nom de route DOIT être ajouté ici.
DEMO_PERIMETER_ROUTE_NAMES = {
    # Modules métier
    "incident_list", "incident_new", "incident_detail",
    "post_list", "directory_home",
    # Compte / navigation
    "home", "profile", "search", "members_list", "logout", "join",
    # Publiques accessibles depuis le site
    "login", "contact", "residence_request", "privacy", "terms", "demo",
    # Techniques (assets, santé) : ne doivent jamais fermer une session démo
    "sw", "favicon", "healthz",
}

# Préfixes de chemins exemptés du contrôle de périmètre. /media/ est servi
# par une vue Django (config/urls.py) et passe donc par tous les middlewares :
# sans exemption, l'affichage d'une photo tuerait la session démo. /static/
# est servi par WhiteNoise en amont de ce middleware, mais on l'exempte aussi
# par sécurité (mise en cache des assets par le service worker).
DEMO_EXEMPT_PATH_PREFIXES = ("/static/", "/media/")


class DemoReadOnlyMiddleware:
    """Passe en lecture seule tout compte de démonstration (`user.is_demo`).

    Deux responsabilités, dans ce seul middleware :
    1. Bloque toute requête de méthode non sûre (POST/PUT/PATCH/DELETE) —
       sauf la déconnexion — sans jamais modifier les vues existantes.
    2. Borne la navigation : un utilisateur démo qui sort du périmètre
       autorisé (liste blanche de noms de routes) est déconnecté, reçoit un
       message d'information et est renvoyé vers la page publique. La
       requête en cours n'est jamais servie en tant qu'utilisateur démo.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(request.user, "is_demo", False):
            return self.get_response(request)

        try:
            url_match = resolve(request.path)
            namespace = url_match.namespace
            url_name = url_match.url_name
        except Resolver404:
            namespace, url_name = None, None

        # L'administration Django est TOUJOURS hors périmètre, même si la
        # liste blanche évoluait par erreur. On teste le namespace, pas le
        # nom de route : `resolve('/admin/login/')` renvoie `url_name='login'`,
        # identique à la route publique `login` — le namespace désambiguïse.
        if namespace == "admin":
            return self._eject_demo(request)

        # Chemins exemptés (assets, médias) : jamais d'éjection, l'affichage
        # d'une photo ne doit pas fermer la session.
        if request.path.startswith(DEMO_EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        if request.method not in SAFE_METHODS:
            # Barrière lecture seule (comportement historique, inchangé).
            if url_name not in DEMO_ALLOWED_ROUTE_NAMES:
                messages.warning(
                    request,
                    "Mode démonstration : les modifications sont désactivées.",
                )
                return redirect(self._safe_referer(request))
            return self.get_response(request)

        # Navigation hors périmètre : fermeture de la session démo.
        if url_name not in DEMO_PERIMETER_ROUTE_NAMES:
            return self._eject_demo(request)

        return self.get_response(request)

    @staticmethod
    def _eject_demo(request):
        """Ferme la session démo et renvoie vers la page publique."""
        logout(request)
        messages.info(request, "Vous avez quitté la démonstration.")
        return redirect(reverse("home"))

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
        # Comptes de démonstration uniquement : interdire la restitution
        # depuis le cache du navigateur (retour arrière / bfcache). Sans ces
        # en-têtes, un retour arrière peut ressortir une page démo du cache
        # alors que la session est fermée. Restreint à `is_demo` (et non à
        # tout utilisateur authentifié) : les résidents normaux gardent le
        # bfcache — sinon chaque retour arrière recharge intégralement la
        # page (perte d'un formulaire en cours, plus lent sur mobile). On
        # épargne aussi /static/ et /media/ : les assets doivent rester mis
        # en cache (service worker, performances).
        if (
            getattr(request.user, "is_demo", False)
            and not request.path.startswith(DEMO_EXEMPT_PATH_PREFIXES)
        ):
            r["Cache-Control"] = "no-store, no-cache, must-revalidate"
            r["Pragma"] = "no-cache"
        return r
