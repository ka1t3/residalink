# Notification e-mail de l'opérateur en cas d'erreur 500

## Problème

En déploiement résidence unique, un résident qui tombe sur une **erreur 500**
voit la page d'erreur Django générique (ou une page blanche), ne sait pas à qui
signaler le problème, et n'écrit probablement à personne : il « réessaiera plus
tard ». L'opérateur ne découvre la panne que **via les logs Coolify**, le jour où
quelqu'un se plaint.

Aucun e-mail n'est envoyé aujourd'hui sur erreur 500. La latence de détection
peut être de plusieurs jours (résidents peu connectés, week-end, vacances).

## Objectifs

1. À chaque **500 en production** : e-mail à l'opérateur avec le contexte
   (chemin, méthode, utilisateur, user-agent, traceback complet).
2. Le résident voit une **page 500 polie en français** (pas de traceback).
3. **Pas de flood** : une même erreur répétée (ex. une panne qui touche 10
   résidents qui rafraîchissent) ne doit pas générer 10 e-mails identiques.
4. En développement (`DEBUG=1`), garder la page technique Django (pas
   d'e-mail) — le développeur a la console.

## Périmètre proposé

### E-mail de notification

- Nouveau gestionnaire `core/views.py::handler500` référencé dans
  `config/urls.py` (**`HANDLERS` n'est pas utilisé sous Django 6 ; le handler
  se définit dans le module urlconf**) et **uniquement si `not DEBUG`** (en
  DEBUG Django affiche sa page technique).
- Destinataire : nouvelle variable d'environnement **`ERROR_NOTIFY_EMAIL`**
  (défaut : `SIGNUP_NOTIFY_EMAIL`), jamais d'adresse de résident.
  `From = DEFAULT_FROM_EMAIL` (règle Brevo existante).
- Corps de l'e-mail (texte brut, pas de Markdown) :
  - horodatage, chemin, méthode, utilisateur (username si authentifié,
    sinon « anonyme »), user-agent ;
  - **traceback complet** (via `log.error` / `sys.exc_info`) ;
  - lien `SITE_URL` + chemin pour reproduction rapide.

### Anti-flood (déduplication)

- Signature de l'erreur : hash (SHA-256, 16 hex) de
  `(classe d'exception, première ligne de traceback)`.
- Nouveau modèle minimal `core/models.py::NotifiedError` :
  `signature` (Char 32, unique), `last_notified_at` (DateTime),
  `count` (PositiveInt, incrémenté à chaque occurrence).
- Règle : **1 e-mail maximum par signature par heure**. Les occurrences
  suivantes dans l'heure n'envoient rien (mais `count` est incrémenté).
- Purge des entrées > 7 jours à chaque écriture (pas de cron).
- Migration `core/0007_notified_error.py`.

### Page 500 résident

- Nouveau template `templates/core/error500.html` (style `auth_base.html`,
  ton existant) : « Une erreur est survenue. L'administrateur de la résidence
  a été prévenu, merci de réessayer dans quelques minutes. » + boutons
  « Retour à l'accueil » et « Actualiser ».
- `status = 500` (pas de 200 pour ne pas empoisonner le cache / les crawlers).

## Fichiers touchés

- `config/settings.py` (`ERROR_NOTIFY_EMAIL`)
- `config/urls.py` (`handler500 = core.handler500`)
- `core/models.py` + `core/migrations/0007_notified_error.py`
- `core/views.py` (`handler500`)
- `templates/core/error500.html` (nouveau)
- `core/tests.py` (tests)
- `README.md` (`ERROR_NOTIFY_EMAIL` documentée — nom seulement)

## Implémentation (réalisée)

- `config/settings.py` : `ERROR_NOTIFY_EMAIL = os.environ.get("ERROR_NOTIFY_EMAIL",
  SIGNUP_NOTIFY_EMAIL)` (pas de `HANDLERS` — Django 6 résout les handlers via
  le module urlconf).
- `config/urls.py` : `handler500 = core.handler500` (Django 6 résout le handler
  depuis le module urlconf ; en DEBUG la page technique Django reste active).
- `core/models.py` : `NotifiedError` (`signature` unique, `last_notified_at`,
  `count`).
- `core/views.py` : `handler500` (dédup à 1/h par signature, purge > 7 jours),
  `_error_signature` (SHA-256 de classe + 1re ligne traceback → 16 hexa),
  `_notify_operator_500` (depuis `DEFAULT_FROM_EMAIL`, reply-to si auth).
- `templates/core/error500.html` : page polie (extends `auth_base.html`).
- `core/tests.py` : 9 tests (`Error500NotificationTests`) — page + e-mail,
  déduplication, nouvelle signature, renotification > 1h, reply-to,
  purge > 7 jours, 404 sans e-mail, **wiring Django 6 urlconf**, **E2E
  stack complète (DEBUG=False, exception réelle, 500 + page + e-mail + traceback)**.
- Total : 43 tests OK, check / makemigrations --check verts.

## Critères d'acceptation

- [x] `DEBUG=0` : une vue qui lève une exception → le résident reçoit une
      **page 500 française** (template `core/error500.html`), status HTTP 500,
      **aucun traceback visible** ;
- [x] `DEBUG=0` : un e-mail part à `ERROR_NOTIFY_EMAIL` (défaut
      `SIGNUP_NOTIFY_EMAIL`) contenant le chemin, l'horodatage, l'utilisateur,
      l'user-agent et le traceback complet ; `From = DEFAULT_FROM_EMAIL` ;
- [x] `DEBUG=0` : 2ᵉ exception **même signature** dans l'heure → **pas de
      2ᵉ e-mail**, `count` = 2 ;
- [x] `DEBUG=0` : exception **différente** (autre signature) → e-mail envoyé ;
- [x] `DEBUG=1` : page technique Django affichée, aucun e-mail ;
- [x] une **404 ne déclenche aucun e-mail** (les 404 sont du business normal :
      contrôle d'accès, routes inconnues) ;
- [x] `uv run manage.py check` et `makemigrations --check` verts ;
- [x] tests : 9 tests + E2E stack complète (`override_settings(DEBUG=False)`
      + `raise_request_exception=False` + vue qui lève une exception) ;
      `core/tests.py::Error500NotificationTests`.

## Hors périmètre

- Signalement des 404 (bruit assuré : les 404 sont un mécanisme de contrôle
  d'accès assumé du projet).
- Sentry ou plateforme tierce (l'e-mail + les logs Coolify suffisent à cette
  échelle).
- Tableau de bord des erreurs dans l'admin (un `ModelAdmin` pourra suivre,
  sans écran dédié pour l'instant).