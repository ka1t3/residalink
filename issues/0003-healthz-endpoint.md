# Endpoint de santé /healthz

## Problème

Il n'existe aucun endpoint de santé sur l'application. Or, pour le déploiement
(Docker + Coolify sur VPS Hetzner) :

- les sondes de supervision externes (Healthchecks.io, UptimeRobot, ou la
  healthcheck de Coolify) n'ont pas de point fiable à interroger ;
- une sonde qui se contenterait du statut HTTP de `/` ne détecterait pas une
  **base de données morte** (l'application gunicorn tourne, mais chaque requête
  métier tombe en 500) ;
- le proxy (Caddy/nginx devant le conteneur) n'a pas de route légère à interroger.

## Objectifs

1. Une route `GET /healthz` **publique, sans authentification**, rapide, idempotente.
2. Détecter aussi la **base de données** (503 si la base ne répond pas) —
   c'est le vrai mode de panne d'un conteneur web.
3. Ne **fuir aucune information sensible** dans la réponse (pas de version,
   pas de réglages, pas de détails de stack).

## Périmètre proposé

- Nouvelle vue fonction `core/views.py::healthz` :
  - exécute une requête minimale (`models.Model.objects.count()` est trop lourd —
    préférer `connection.cursor()` + `SELECT 1`, ou `BaseCommand.check_databases`-like) ;
  - si OK : **200** `{"status": "ok"}` (JSON, `Content-Type: application/json`) ;
  - si la base ne répond pas : **503** `{"status": "error"}` ;
  - jamais de traceback, d'environ, de version Django dans la réponse.
- Nouvelle route dans `config/urls.py` : `path("healthz", core.healthz, name="healthz")`.
- Pas de lien vers `/healthz` dans les templates (outil d'infrastructure, pas
  de page utilisateur).
- Compatibles existants :
  - `DemoReadOnlyMiddleware` : GET = méthode sûre, non concernée ;
  - `ModuleGateMiddleware` : ne porte que sur `/incidents/`, `/mur/`, `/carnet/` ;
  - CSP : aucune ressource externe.

## Fichiers touchés

- `core/views.py` (vue `healthz`)
- `config/urls.py` (route)
- `core/tests.py` (tests)

## Critères d'acceptation

- [x] `GET /healthz` → **200**, corps JSON `{"status": "ok"}`, sans requête
      d'authentification, sans cookie de session requis ;
- [x] `GET /healthz` avec la base simulée en panne (mock de l'exception de
      connexion) → **503**, corps JSON `{"status": "error"}`, **pas de traceback** ;
- [x] la réponse ne contient ni version de Django, ni `SECRET_KEY`, ni
      `SITE_URL`, ni autre valeur de `settings` ;
- [x] `GET /healthz` n'apparaît dans aucun template (pas de lien UI) ;
- [x] `uv run manage.py check` et `makemigrations --check` verts ;
- [x] tests : 3 tests (200 base OK / 503 base HS / pas de fuite d'info) dans
      `core/tests.py` (`HealthzTests`).

## Implémentation (réalisée)

- `core/views.py` : vue `healthz` — ouvre un curseur et exécute `SELECT 1` ;
  `DatabaseError` → `JsonResponse({"status": "error"}, status=503)`, sinon
  `JsonResponse({"status": "ok"})`.
- `config/urls.py` : `path("healthz", core.healthz, name="healthz")` (non
  authentifiée, juste après `favicon.ico`).
- `core/tests.py` : `HealthzTests` (200 OK / 503 base HS via mock
  `django.db.connection.cursor` / pas de fuite d'info). Suite complète :
  37 tests verts.

## Hors périmètre

- Distinction liveness/readiness (sémantique Kubernetes) — inutile pour
  Coolify/Docker tel que configuré.
- Rapport détaillé des dépendances (disque média, SMTP, queue) — un 200/503
  binaire suffit pour la supervision ;
- Authentification de l'endpoint (public mais sans information sensible).