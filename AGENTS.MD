# Residalink

SaaS de gestion **quotidienne** de copropriété (residalink.com), complémentaire au syndic — **pas** de comptabilité, de juridique ni d'assemblées générales. Trois usages : signaler et suivre les incidents d'immeuble, communiquer entre voisins (mur), garder la mémoire de la résidence (contacts, infos pratiques, travaux). Cible : résidents peu à l'aise avec l'informatique → **la simplicité prime toujours sur la richesse fonctionnelle**.

Développeur unique. Projet open source sous **licence AGPL v3** (fichier `LICENSE`).

## Stack & outillage

- **Python / Django** (monolithe modulaire). Base **PostgreSQL**.
- **Gestion des dépendances : `uv` uniquement** (`pyproject.toml` + `uv.lock`). **Ne jamais utiliser `pip`.**
- Front : **templates Django + Tailwind (CDN) + police Inter**. Très peu de JS (pas de framework front). HTMX présent mais quasi inutilisé.
- Statique servi par **WhiteNoise**. Icônes : **Lucide** (CDN unpkg).
- Déploiement : **VPS Hetzner + Coolify** (Docker), HTTPS Let's Encrypt. E-mails via **Brevo** (SMTP).

Commandes usuelles (toujours préfixer par `uv run`) :
```bash
uv sync
uv run manage.py runserver
uv run manage.py makemigrations
uv run manage.py makemigrations --check   # doit dire "No changes detected" avant un commit
uv run manage.py migrate
uv run manage.py check
uv run manage.py bootstrap                 # crée résidence de démo + catégories
```

## Architecture

- **Une app Django = un module produit.** Apps existantes :
  - `core` : modèles `Residence`, `User` (custom : `residence`, `display_name`, `lot`, préférences de notif), `ResidenceModule` ; auth ; recherche globale (`core/search.py`) ; middlewares.
  - `incidents` : signalements avec cycle **Signalé → Pris en compte → En cours → Résolu**, `IncidentCategory`, `IncidentPhoto`, `IncidentUpdate` (journal).
  - `wall` : `Post` (types alerte/info/événement/entraide), commentaires, `PostPhoto`.
  - `directory` : carnet, **affiché sous le libellé « Information générale »** (l'URL reste `/carnet/`, le nom de route `directory_home` — ne pas renommer les routes).
- **Multi-tenant** : base partagée, **`residence_id` sur toutes les tables métier**. Toute requête métier doit être bornée à la résidence de l'utilisateur.
- **Activation par module** : table `ResidenceModule (residence, module, enabled)`. Une page de module doit vérifier que le module est actif pour la résidence.
- **Rôle métier `conseil_syndical`** = **groupe Django**, exposé par la propriété `User.is_council`. **Distinct de l'admin Django.** Les membres du CS agissent **depuis l'app** (changer le statut d'un incident, épingler un post, éditer le carnet), **sans** accès à l'admin. L'admin Django ne sert qu'à l'opérateur (créer une résidence, promouvoir un membre CS, activer des modules, gérer les catégories).

## Conventions de code

- **Tout le texte d'interface est en français.**
- **Formulaires HTML natifs + POST classique** (pas d'API REST, pas de vues génériques `UpdateView`/mixins). Les vues sont des **fonctions**.
- **Sécurité par queryset**, pas par mixin. Pour restreindre à l'auteur et à la résidence :
  ```python
  post = get_object_or_404(_residence_posts(request), pk=pk, author=request.user)
  ```
  Un non-auteur / une autre résidence / une requête forgée doit obtenir un **404** (en GET comme en POST).
- **Icônes = Lucide**, rendues via `<i data-lucide="nom"></i>` (jamais `{{ obj.icon }}` en texte brut). `lucide.createIcons()` est appelé dans `base.html`. Le champ `IncidentCategory.icon` contient un **nom d'icône Lucide**, pas un émoji. **Vérifier chaque nom sur lucide.dev/icons** avant usage — un nom inexistant s'affiche vide, sans erreur.
- **Contenu Markdown du mur** : rendu via le filtre `render_md` (`wall/templatetags/wall_extras.py`), qui fait `markdown` **puis** assainit avec **`nh3`**. **Toujours** afficher le contenu utilisateur via `render_md` (jamais `|safe` ni HTML brut) — c'est la protection XSS. Dépendances : `markdown`, `nh3`.
- Formatage : privilégier la sobriété, cohérence avec l'existant (palette neutre + accent émeraude, coins arrondis, cartes blanches, bordures fines).

## Sécurité (critique)

- **En-têtes de sécurité** posés par `core/middleware.py` → `SecurityHeadersMiddleware` (CSP, Permissions-Policy) + réglages `settings.py` (`X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY`, `SECURE_CONTENT_TYPE_NOSNIFF`, HSTS en prod).
- **CSP** : sources externes **autorisées** = `cdn.tailwindcss.com`, `unpkg.com` (`script-src`), `fonts.googleapis.com` (`style-src`), `fonts.gstatic.com` (`font-src`), et `img-src 'self' data: blob:`.
  → **Toute nouvelle ressource externe (CDN, image distante, script) DOIT être ajoutée à la CSP**, sinon elle est bloquée **en production** (souvent invisible en local). Préférer **héberger en local** dans `/static` plutôt qu'ajouter un CDN.
- **Jamais de secret dans le code ni committé.** Les secrets vivent en **variables d'environnement Coolify** : `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `DATABASE_URL`, `MEDIA_ROOT`, `EMAIL_HOST/PORT/USER/PASSWORD`, `DEFAULT_FROM_EMAIL`, `SIGNUP_NOTIFY_EMAIL`. Dans un README/doc, ne mettre que les **noms**, jamais les valeurs.

## Médias / photos (fragile — suivre exactement)

Ce pipeline a déjà causé des pertes de fichiers. Règles impératives :

- **Noms de fichiers uniques** via `upload_to` basé sur **UUID** (jamais le nom d'origine → risque d'écrasement). Rangement par résidence, ex. `incidents/{residence_id}/{uuid}.jpg`.
- **Nettoyage disque à la suppression** : signal `post_delete` qui appelle `instance.image.delete(save=False)`. Signaux branchés dans les `AppConfig.ready()`.
- **Piège** : `QuerySet.delete()` en masse **ne déclenche pas** `post_delete` → fichiers orphelins. Pour supprimer des photos, **boucler et appeler `.delete()` objet par objet** :
  ```python
  for photo in IncidentPhoto.objects.filter(pk__in=ids, incident=incident):
      photo.delete()   # déclenche le signal → supprime le fichier physique
  ```
- `MEDIA_ROOT=/app/media`, monté sur un **volume persistant Coolify** (sinon les photos disparaissent à chaque redéploiement).
- Les médias sont servis **en production** par une route `re_path(r"^media/…", serve, {document_root: MEDIA_ROOT})` **inconditionnelle** dans `urls.py` (le `if DEBUG` d'origine ne servait pas `/media` en prod).
- Sur chaque `<img>` de photo utilisateur, prévoir un `onerror` qui masque proprement l'image si le fichier manque (pas de cadre cassé).

## PWA

- `static/manifest.json` + `static/sw.js` + icônes. Le **Service Worker est servi à la racine** (`/sw.js`) par une vue Django qui renvoie le JS avec l'en-tête `Service-Worker-Allowed: /` (nécessaire pour contrôler tout le site).
- `sw.js` : **network-first**, ignore le cross-origin, cache nommé `resida-vN`.
- **À chaque modification de `sw.js`, incrémenter le numéro de version du cache** (`resida-v2` → `v3`…), sinon les navigateurs des résidents gardent l'ancienne version.

## Déploiement

- **Merge dans `main` = déploiement automatique en production** via webhook Coolify. Ne merger que du code **testé en local**.
- Le Dockerfile lance `migrate` et `collectstatic` au déploiement. **Toute migration doit être committée dans la PR.**
- Après déploiement, vérifier les logs Coolify (build vert, migrations `… OK`).

## Workflow attendu

1. Créer une **branche** à partir de `main` à jour.
2. Développer, **commiter par lot** (un commit = un changement cohérent).
3. Tester en local : `uv run manage.py check`, `makemigrations --check`, **et tour des écrans à l'œil** (console F12 ouverte pour repérer les blocages CSP).
4. PR → merge dans `main` → déploiement auto → **re-tester en production** (surtout ce qui touche CSP, Service Worker, e-mails Brevo).

## Vérification (ne pas se fier au « c'est fait »)

- « Ça compile / le check passe » **ne veut pas dire** « c'est réussi visuellement ». Toujours **regarder le rendu**.
- Avant d'affirmer une exhaustivité (« plus aucune occurrence »), **le prouver avec `grep`**. Exemple pour les icônes en texte brut :
  ```bash
  grep -rn "\.icon" templates/    # toute ligne {{ ...icon }} sans data-lucide = bug
  ```
- Après une suppression de photo, **vérifier le disque** (`ls media/...`) que le fichier a bien disparu.

## À NE PAS faire

- ❌ Utiliser `pip` (toujours `uv`).
- ❌ Réimplémenter une fonctionnalité déjà présente sans avoir vérifié qu'elle n'existe pas (édition de posts/incidents, `render_md`, `upload_to` UUID, signaux de nettoyage… existent déjà).
- ❌ Supprimer des photos via `filter(...).delete()` en masse (contourne le signal → fichiers orphelins).
- ❌ Ajouter un CDN/ressource externe sans mettre à jour la CSP (`core/middleware.py`).
- ❌ Renommer les routes existantes (`directory_home`, etc.) — seul l'affichage change, pas les URLs.
- ❌ Afficher du contenu utilisateur sans `render_md` (risque XSS).
- ❌ Donner accès à l'admin Django au conseil syndical (le CS agit depuis l'app).
- ❌ Committer un secret ou écrire une valeur secrète dans un fichier.