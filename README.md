[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Django](https://img.shields.io/badge/Django-6-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PWA](https://img.shields.io/badge/PWA-installable-5A0FC8)](https://web.dev/progressive-web-apps/)

# Residalink

**La vie de votre immeuble, enfin au clair.**

Residalink est un outil **100 % gratuit et open source** pour gérer le quotidien d'une copropriété — signaler et suivre les incidents, échanger entre voisins, et garder la mémoire de la résidence. Il vient **en complément du syndic** : pas de comptabilité, pas de juridique, pas d'assemblées générales. Juste ce qui rend la vie d'un immeuble plus simple, au jour le jour.

Il est pensé pour des résidents **peu à l'aise avec l'informatique** : la simplicité prime toujours sur la richesse fonctionnelle.

**Essayez-le ici : [residalink.com](https://residalink.com)**

**Ce projet vit grâce à ses contributeurs — [venez contribuer](CONTRIBUTING.md) !** Vous pouvez aussi [soutenir le projet financièrement](https://liberapay.com/residalink/donate).

---

## Ce que ça fait

Residalink s'organise autour de trois modules, activables par résidence.

### Le suivi des incidents

Un problème sur une partie commune ? On le signale **une seule fois**, et chacun suit son avancement — de *Signalé* à *Pris en compte*, *En cours*, puis *Résolu*. Fini les doublons et les « alors, cet ascenseur ? ». Chaque signalement a son journal, ses photos, ses catégories, et notifie les personnes concernées.

### Le mur de la résidence

Annonces, entraide, petits événements : les messages qui comptent restent **visibles et à leur place**, au lieu de défiler et de disparaître dans un fil de discussion. Publications typées (alerte, info, événement, entraide), commentaires, photos, épinglage par le conseil syndical.

### L'information générale

Contacts utiles, infos pratiques, travaux en cours : tout est **rangé au même endroit** et reste accessible, même quand les voisins changent.

Et aussi : **recherche globale**, **notifications e-mail** désactivables, **application installable** (PWA) sur l'écran d'accueil, rôle **conseil syndical** pour la gestion, **mode démonstration** en lecture seule (`/demo/`) — le tout dans une interface sobre et responsive.

---

## Sous le capot

Residalink est un **monolithe Django modulaire**, multi-résidences (chaque résidence a son espace privé, isolé par `residence_id`).

| Brique | Choix |
| --- | --- |
| Backend | **Django** (apps `core`, `incidents`, `wall`, `directory`) |
| Base de données | **PostgreSQL** (production) · **SQLite** (local) |
| Dépendances | **[uv](https://docs.astral.sh/uv/)** (`pyproject.toml` + `uv.lock`) |
| Frontend | Templates Django + **Tailwind CSS** + Inter + icônes **Lucide** |
| Statique | **WhiteNoise** |
| E-mails | **Brevo** (SMTP) |
| Sécurité | **django-axes** (anti force brute), **nh3** (assainissement du contenu) |
| Déploiement | **Docker** + **Gunicorn** sur **Coolify** (VPS Hetzner) |
| Licence | **AGPL v3** |

---

## Lancer le projet en local

1. **Forkez** ce dépôt, `git clone`-le, et entrez dans le dossier `residalink`.
2. Installez **Python 3.12+** et **[uv](https://docs.astral.sh/uv/getting-started/installation/)**.
3. Installez les dépendances :
   ```bash
   uv sync
   ```
4. Créez un fichier `.env` à la racine (voir [Variables d'environnement](#variables-denvironnement)).
5. Appliquez les migrations :
   ```bash
   uv run manage.py migrate
   ```
6. Créez une résidence de démonstration (avec ses modules et catégories) :
   ```bash
   uv run manage.py bootstrap "Résidence de démo"
   ```
7. Créez un compte administrateur :
   ```bash
   uv run manage.py createsuperuser
   ```
8. Lancez le serveur de développement :
   ```bash
   uv run manage.py runserver
   ```
9. Rendez-vous sur **<http://localhost:8000/>**

> Utilisez **toujours** `uv` (jamais `pip`) pour rester aligné sur le `uv.lock` du projet.

---

## Variables d'environnement

En développement, des valeurs par défaut suffisent. En production, définissez ces variables (côté hébergeur — **jamais dans le code**) :

| Variable | Rôle |
| --- | --- |
| `SECRET_KEY` | Clé secrète Django |
| `DEBUG` | `0` en production |
| `ALLOWED_HOSTS` | Domaines autorisés |
| `CSRF_TRUSTED_ORIGINS` | Origines de confiance CSRF |
| `SITE_URL` | URL publique du site |
| `DATABASE_URL` | Connexion PostgreSQL |
| `MEDIA_ROOT` | Dossier des médias (volume persistant) |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP Brevo |
| `DEFAULT_FROM_EMAIL` | Expéditeur des e-mails |
| `SIGNUP_NOTIFY_EMAIL` | Destinataire des demandes de création de résidence |
| `ERROR_NOTIFY_EMAIL` | Destinataire des alertes d'erreur 500 |
| `OPEN_REGISTRATION` | `0` pour masquer le parcours « créer une résidence » (mode résidence unique) |
| `DONATE_URL` | URL du lien de don (défaut Liberapay ; vide = masqué) |

---

## Structure du projet

```
residalink/
├── config/        # Configuration Django (settings, urls)
├── core/          # Résidences, comptes, rôles, recherche, middlewares, PWA
├── incidents/     # Signalements, catégories, suivi, photos
├── wall/          # Mur d'échanges, commentaires, photos
├── directory/     # Carnet d'infos (« Information générale »)
├── templates/     # Templates Django + landing publique
├── static/        # Tailwind (CDN), icônes, manifest PWA, service worker
├── issues/        # Notes de suivi des évolutions
└── AGENTS.MD      # Conventions du projet (utile aux agents de code)
```

Le rôle métier **« conseil syndical »** est un groupe Django (propriété `is_council`), **distinct de l'admin Django** : ses membres agissent depuis l'application (statuts d'incidents, épinglage, carnet), sans accès à l'administration.

---

## Contribuer

Toute aide est la bienvenue — code, idées, retours d'usage, traductions, documentation. Le meilleur point de départ : **[le guide de contribution](CONTRIBUTING.md)**.

Vous pouvez aussi simplement [ouvrir une issue](../../issues/new) pour signaler un bug, proposer une amélioration, ou raconter comment votre résidence utilise (ou pourrait utiliser) l'outil. Les retours d'usage réels valent de l'or.

---

## Licence

Residalink est distribué sous licence **[GNU AGPL v3](LICENSE)**. Le code est libre : vous pouvez l'étudier, le modifier et l'héberger vous-même. Toute version déployée comme service doit rester ouverte, dans le même esprit.

---

<p align="center"><em>Fait entre voisins, pour les voisins. </em></p>
