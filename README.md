# Ma Résidence — MVP

Plateforme de vie quotidienne pour copropriétés : incidents, mur d'actualité, carnet de santé.
Django 6 · templates + Tailwind (CDN) · SQLite en dev, PostgreSQL en production.

## Démarrer en local (5 minutes)

```bash
uv sync
uv run manage.py migrate
uv run manage.py bootstrap "Résidence Les Tilleuls"   # affiche le code d'invitation
uv run manage.py createsuperuser                       # votre compte admin
uv run manage.py runserver
```

- Site : http://localhost:8000 → « Rejoindre ma résidence » avec le code affiché
- Admin : http://localhost:8000/admin (gérer résidence, membres, modules, carnet)
- Promouvoir un membre au conseil syndical : admin → Utilisateurs → groupes → `conseil_syndical`
- Les emails s'affichent dans la console en dev.

## Déployer sur Hetzner + Coolify

1. VPS Hetzner CX22 (~4 €/mois), installer Coolify : `curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash`
2. Dans Coolify : créer une base **PostgreSQL**, puis une application depuis ce dépôt Git (build : Dockerfile).
3. Variables d'environnement de l'application :

```
SECRET_KEY=<50 caractères aléatoires>
DEBUG=0
ALLOWED_HOSTS=votredomaine.fr
CSRF_TRUSTED_ORIGINS=https://votredomaine.fr
SITE_URL=https://votredomaine.fr
DATABASE_URL=postgres://... (fourni par Coolify)
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_HOST_USER=<identifiant Brevo>
EMAIL_HOST_PASSWORD=<clé SMTP Brevo>
DEFAULT_FROM_EMAIL=Ma Résidence <notifications@votredomaine.fr>
MEDIA_ROOT=/data/media
```

4. Monter un volume persistant sur `/data` (photos d'incidents).
5. Pointer le domaine vers le VPS ; Coolify gère le HTTPS automatiquement.
6. Sur le serveur : `python manage.py bootstrap "Nom de la résidence"` puis `createsuperuser` (via le terminal Coolify).
7. Brevo : configurer SPF/DKIM sur le domaine avant d'inviter les résidents (sinon → spam).

## Architecture

Monolithe modulaire : une app Django = un module produit (`incidents`, `wall`, `directory`).
`core` porte la résidence, les comptes et l'activation des modules (`ResidenceModule`).
Toutes les tables métier portent `residence_id` : le multi-résidences est structurellement prêt.
Le middleware `ModuleGateMiddleware` masque et bloque les modules désactivés.

Ajouter un module futur (devis, réservations…) = créer une app, l'ajouter à
`ResidenceModule.MODULES`, `MODULE_PREFIXES` (middleware) et la navigation. Rien d'autre.
