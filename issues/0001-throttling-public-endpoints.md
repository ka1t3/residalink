# Throttling des endpoints publics : connexion et demande de résidence

## Problème

Deux endpoints publics exposés au monde entier sont sans protection contre l'automatisation :

### 1. `/connexion/` — pas de protection anti force brute

- Vue `LoginView` standard Django, sans limitation de tentatives.
- L'identifiant de connexion **est l'adresse e-mail** (`username = email`, cf. `JoinForm.save()`),
  donc facilement connu ou devinable (e-mail visible dans les notifications, dans la résidence,
  etc.).
- Conséquence : un attaquant peut tester des milliers de mots de passe par IP sans blocage.
  Aucun `django-axes`, aucun cooldown, aucun signal d'alerte.

### 2. `/demande-residence/` — amplificateur d'e-mails sans anti-spam

- `core/views.py::residence_request` est un `@require_POST` public qui envoie un e-mail
  **à chaque soumission valide**, avec l'adresse du visiteur en `reply_to`.
- Aucune mesure anti-spam (ni honeypot, ni délai, ni limitation) contrairement à
  `/contact/` qui a déjà honeypot + horodatage signé.
- Conséquences :
  - **bombardement** de la boîte de l'opérateur (`SIGNUP_NOTIFY_EMAIL`) ;
  - **relai d'e-mails** : un bot peut faire passer ses propres messages via l'infra
    Residalink (délivérabilité Brevo / SPF-DKIM au profit de l'attaquant) ;
  - coût serveur (connexion SMTP par requête).

À noter : le délai « 3 secondes » de `/contact/` n'est pas une vraie limitation de débit
(3 s d'attente contournables, un re-GET du formulaire régénère le timestamp) — il est
gardé en l'état pour cette issue, son durcissement éventuel pourra suivre.

## Objectifs

1. Bloquer la force brute sur la connexion (verrouillage progressif par IP + identifiant).
2. Rendre le formulaire de demande de résidence aussi protégé que le formulaire de contact,
   plus une vraie limitation par IP.

## Périmètre proposé

### Connexion (django-axes)

- Ajouter `django-axes` (`uv add django-axes`) :
  - verrouillage après **5 échecs** par (IP, username) pendant **10 min** ;
  - messages d'échec existants conservés, un message « trop de tentatives » affiché
    sur le template de login.
- Alternative sans dépendance : middleware maison de cooldown par IP (p.ex. sauvegarder
  l'horodatage des échecs en cache mémoire). Plus léger, moins lisible, et moins fiable
  en multi-workers gunicorn. **Recommandation : django-axes** — éprouvé, 3 lignes de config.
- Vérifier que le mode démo n'est pas impacté (connexion du compte démo non concernée :
  le compte démo n'a pas de mot de passe utilisable et `/demo/` ne passe pas par le
  formulaire de connexion).

### Demande de résidence

Réutiliser le pattern déjà présent dans `core/views.py::contact` (pas de réimplémentation) :

- **honeypot** champ `website` (un bot qui le remplit est accepté silencieusement) ;
- **horodatage signé** (`signing.TimestampSigner`) avec délai minimal ;
- **nouveau — vraie limitation par IP** : au plus **1 demande / IP / heure**.
  Stockage le plus simple et fiable en Docker single-container : une table légère en base
  (ou réutiliser le cache, en étant conscient qu'un cache mémoire est par-worker sous
  gunicorn). À trancher à l'implémentation ; si table en base, prévoir une purge des
  entrées > 1 h à l'écriture (pas de cron).
- En cas de limitation : renvoyer la landing sans erreur explicite (« demande déjà reçue »)
  pour ne pas confirmer de quoi l'IP est « accusée ».

## Fichiers touchés

- `pyproject.toml` / `uv.lock` (dépendance `django-axes`)
- `config/settings.py` (app, middleware, backends, config axes)
- `core/models.py` + `core/migrations/0006_*.py` (`PublicRequestCooldown`)
- `core/views.py` (`residence_request`, `home`, `login()` explicite)
- `core/tests.py` (`LoginThrottleTests`, `ResidenceRequestThrottleTests`)
- `templates/landing.html` (champ `ts` + honeypot `website`)
- `templates/core/axes_lockout.html` (nouveau, page 429)

## Critères d'acceptation

- [x] 5 échecs successifs (même IP + même e-mail) → le 5ᵉ essai affiche le message de
      verrouillage (HTTP 429) et le compte reste verrouillé ensuite, même avec le bon
      mot de passe ; sans e-mail ni création de compte. *(Note : `django-axes` affiche le
      message dès que la limite est atteinte, i.e. au 5ᵉ échec, pas au 6ᵉ.)*
- [x] une *autre* adresse (même IP) se connecte normalement après 5 échecs sur une
      première adresse (verrouillage par couple (e-mail, IP), pas par IP seule) ;
- [x] le compte démo (`/demo/`) n'est pas impacté par le verrouillage ;
- [x] `uv run manage.py check` et `makemigrations --check` verts ;
- [x] `/demande-residence/` : un POST avec honeypot rempli est accepté silencieusement
      (aucun e-mail envoyé, aucun enregistrement de limitation) ;
- [x] 2ᵉ demande valide depuis la même IP dans l'heure → aucun e-mail, pas d'erreur
      explicite (redirection silencieuse « envoyée ») ;
- [x] un horodatage signé trop récent (< 3 s) ou forgé → abandon silencieux ;
- [x] en session démo, le formulaire public continue de fonctionner
      (`DEMO_ALLOWED_ROUTE_NAMES` contient déjà `residence_request`) ;
- [x] tests : `core/tests.py::LoginThrottleTests` + `ResidenceRequestThrottleTests`
      (10 tests), suite complète `uv run manage.py test` verte (34 tests) ;
- [x] tour des écrans : `/connexion/` (verrouillage 429), `/?creer` (honeypot + ts
      cachés), `/demo/` — aucun blocage CSP.

## Implémentation (réalisée)

- **`django-axes` 8.3.1** ajouté (`pyproject.toml` / `uv.lock`).
- `config/settings.py` :
  - `axes` dans `INSTALLED_APPS` (après `django.contrib.admin`) ;
  - `axes.middleware.AxesMiddleware` dans `MIDDLEWARE` (après `AuthenticationMiddleware`) ;
  - `AUTHENTICATION_BACKENDS = ["axes.backends.AxesBackend", ModelBackend]` ;
  - `AXES_FAILURE_LIMIT = 5`, `AXES_COOLOFF_TIME = 10` (min),
    `AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]` (mode combinaison :
    verrouille le couple (e-mail, IP), pas l'IP seule → pas d'effet de bord sur les
    voisins de la même résidence derrière un même NAT),
    `AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False` (le cooldown ne se
    réinitialise pas à chaque tentative verrouillée, et le middleware affiche le
    template de lockout), `AXES_LOCKOUT_TEMPLATE = "core/axes_lockout.html"`,
    `AXES_HTTP_RESPONSE_CODE = 429`.
- `core/models.py` : nouveau modèle `PublicRequestCooldown` (key, ip, last_at,
  unique (key, ip)) + migration `core/0006`.
- `core/views.py` :
  - `residence_request` protégé : honeypot `website` → abandon silencieux ;
    horodatage signé `ts` (≥ 3 s, sinon abandon silencieux) ; limitation 1 / IP / heure
    via `PublicRequestCooldown` (purge des entrées > 1 h à l'écriture, pas de cron) ;
    un bot est toujours renvoyé sur `?envoye=1#creer` (aucune erreur confirmée).
  - `home()` passe `ts` au template landing.
  - `login(request, user, backend="django.contrib.auth.backends.ModelBackend")` : le
    backend est désormais explicite (requis par Django 6 dès que plusieurs backends
    sont configurés) — concerne `join()` et `demo()`.
- `templates/landing.html` : champ caché `ts` + honeypot `website` (class `hidden`).
- `templates/core/axes_lockout.html` : nouveau (page 429 en français, liens
  « réinitialiser le mot de passe » + « réessayer »).

## Hors périmètre

- Durcissement du délai 3 s de `/contact/` (voir « À noter »).
- Rate-limiting global (WAF, nginx, Coolify) : à évaluer séparément au niveau VPS.
- Les autres points d'ordre sécurité de l'audit (CSP/Tailwind auto-hébergé, codes
  d'invitation, GDPR, pagination) : issues distinctes.