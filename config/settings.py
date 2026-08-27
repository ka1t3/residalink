"""
Réglages Django — Residalink (nom de travail, à renommer).
Toute la configuration sensible passe par des variables d'environnement.
En local : aucune variable nécessaire, tout a un défaut raisonnable.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "axes",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "incidents",
    "wall",
    "directory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Doit venir après MessageMiddleware : ce middleware appelle
    # `messages.warning()`, qui nécessite que `request._messages` soit déjà
    # initialisé. Doit aussi venir après AuthenticationMiddleware pour
    # disposer de `request.user`.
    "core.middleware.DemoReadOnlyMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.ModuleGateMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.active_modules",
                "core.context_processors.donate_url",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL si DATABASE_URL est défini (production), sinon SQLite (dev local).
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 Mo
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 Mo

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Emails : console en dev, SMTP (Brevo) en production.
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Ma Résidence <no-reply@example.com>")
SIGNUP_NOTIFY_EMAIL = os.environ.get("SIGNUP_NOTIFY_EMAIL", DEFAULT_FROM_EMAIL)

# Notification des erreurs 500 (production uniquement) : destinataire de
# l'e-mail d'alerte (défaut : SIGNUP_NOTIFY_EMAIL).
ERROR_NOTIFY_EMAIL = os.environ.get("ERROR_NOTIFY_EMAIL", SIGNUP_NOTIFY_EMAIL)

# ---------------------------------------------------------------------------
# django-axes : protection anti force brute sur la connexion
# ---------------------------------------------------------------------------
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 10                          # minutes
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
# Reset du cooldown : sinon le compte est définitivement bloqué
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
# Template affiché quand le compte est verrouillé
AXES_LOCKOUT_TEMPLATE = "core/axes_lockout.html"
AXES_HTTP_RESPONSE_CODE = 429

# URL externe de don (lien "Offrir un café" sur la landing). Vide = lien masqué.
DONATE_URL = os.environ.get("DONATE_URL", "")

X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
