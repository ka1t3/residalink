# Residalink

Outil de gestion quotidienne pour copropriétés : signalement d'incidents, mur d'actualité et carnet de santé de l'immeuble.

## Stack technique

| Composant | Choix |
|---|---|
| Backend | Django 6, Python 3.12 |
| Gestion des dépendances | uv |
| Base de données | SQLite (dev) · PostgreSQL (production) |
| CSS / icônes | Tailwind CSS (CDN) · Lucide Icons (CDN) |
| Fichiers statiques | Whitenoise |
| Serveur WSGI | Gunicorn |
| Conteneurisation | Docker (image `uv:python3.12-bookworm-slim`) |
| Hébergement | Coolify |

## Installation locale

```bash
uv sync
uv run manage.py migrate
uv run manage.py bootstrap "Résidence Les Tilleuls"   # crée la résidence et affiche le code d'invitation
uv run manage.py createsuperuser
uv run manage.py runserver
```

- Accès résidents : `http://localhost:8000` → « Rejoindre ma résidence » avec le code affiché
- Interface admin : `http://localhost:8000/admin`
- Promouvoir un membre au conseil syndical : Admin → Utilisateurs → groupes → `conseil_syndical`
- Les e-mails s'affichent dans la console en développement (pas d'SMTP requis)

## Structure du projet

```
residalink/
├── config/        # Configuration Django (settings, urls, wsgi, asgi)
├── core/          # Résidences, comptes utilisateurs, activation des modules, notifications, recherche
├── incidents/     # Signalement et suivi d'incidents (catégories, statuts, photos, journal)
├── wall/          # Mur d'actualité : posts, commentaires, réactions, alertes
├── directory/     # Carnet de santé : contacts, informations pratiques, historique des travaux
└── templates/     # Templates HTML globaux
```

## Déploiement (Docker + Coolify)

Le `Dockerfile` collecte les fichiers statiques au build, puis exécute `migrate` et `gunicorn` au démarrage du conteneur. Aucune commande manuelle n'est nécessaire pour le déploiement courant.

**Procédure initiale :**

1. Créer une application depuis ce dépôt Git dans Coolify (build : Dockerfile)
2. Créer une base **PostgreSQL** gérée dans Coolify et récupérer son `DATABASE_URL`
3. Renseigner les variables d'environnement (voir ci-dessous)
4. Monter un volume persistant sur `/data` pour conserver les photos entre les redéploiements
5. Coolify gère le HTTPS et le DNS automatiquement
6. Via le terminal Coolify, initialiser la résidence :
   ```bash
   python manage.py bootstrap "Nom de la résidence"
   python manage.py createsuperuser
   ```

### Variables d'environnement

| Variable | Description |
|---|---|
| `SECRET_KEY` | Clé secrète Django (50 caractères aléatoires minimum) |
| `DEBUG` | `0` en production |
| `ALLOWED_HOSTS` | Domaine(s) autorisé(s), séparés par des virgules |
| `CSRF_TRUSTED_ORIGINS` | Origine(s) de confiance pour le CSRF (ex. `https://votredomaine.fr`) |
| `SITE_URL` | URL publique complète (utilisée dans les e-mails) |
| `DATABASE_URL` | URL de connexion PostgreSQL (fournie par Coolify) |
| `EMAIL_HOST` | Serveur SMTP sortant |
| `EMAIL_PORT` | Port SMTP (défaut : `587`) |
| `EMAIL_HOST_USER` | Identifiant SMTP |
| `EMAIL_HOST_PASSWORD` | Mot de passe / clé SMTP |
| `DEFAULT_FROM_EMAIL` | Expéditeur affiché dans les notifications |
| `MEDIA_ROOT` | Chemin de stockage des fichiers uploadés (ex. `/data/media`) |
| `DONATE_URL` | URL externe du lien de don « Offrir un café » sur la landing (vide = lien masqué) |

## Ajouter un module

L'architecture est un monolithe modulaire : chaque module est une app Django indépendante. Toutes les tables métier portent un `residence_id`, rendant le multi-résidences structurellement opérationnel. Le middleware `ModuleGateMiddleware` bloque automatiquement l'accès aux modules désactivés.

Pour ajouter un nouveau module (ex. réservations, devis) :

1. Créer une app Django (`python manage.py startapp <nom>`)
2. Ajouter le slug dans `ResidenceModule.MODULES` (`core/models.py`)
3. Déclarer le préfixe d'URL dans `MODULE_PREFIXES` (`core/middleware.py`)
4. Ajouter l'entrée de navigation dans `templates/base.html`

## Licence

Ce projet est distribué sous licence **GNU AGPL v3**. Voir le fichier [LICENSE](LICENSE).
