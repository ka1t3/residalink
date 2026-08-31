# Residalink

SaaS de gestion **quotidienne** de copropriété (residalink.com), complémentaire au syndic. Il n'y a  **pas** de comptabilité, de juridique ni d'assemblées générales. Trois usages : signaler et suivre les incidents d'immeuble, communiquer entre voisins (mur), garder la mémoire de la résidence (contacts, infos pratiques, travaux). Cible : résidents peu à l'aise avec l'informatique → **la simplicité prime toujours sur la richesse fonctionnelle**.

Développeur unique. Projet open source sous **licence AGPL v3** (fichier `LICENSE`).

## Stack & outillage

- **Python 3.12 / Django 6.0.x** (monolithe modulaire). Vérifier la version avant de générer du code : les idiomes Django 4/5 obsolètes ne passent plus.
- **Base de données : PostgreSQL en production** (via `DATABASE_URL`), **SQLite en local** par défaut si la variable n'est pas définie (`config/settings.py`).
  → Une migration ou un test qui passe en local n'est **pas** validé pour la production : types de colonnes, contraintes uniques ajoutées sur des données existantes, `NOT NULL` sans défaut, et sensibilité à la casse de `icontains` (insensible en SQLite, sensible en Postgres → la recherche globale peut se comporter différemment en prod). En cas de doute sérieux sur une migration, lancer un Postgres local et pointer `DATABASE_URL` dessus avant de merger.
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
uv run manage.py test                     # doit être vert avant toute PR

uv run manage.py bootstrap "Nom de la résidence"   # nom = argument POSITIONNEL OBLIGATOIRE
uv run manage.py reset_demo                        # réinitialise la résidence de démonstration
uv run manage.py usage_report                      # usage réel, hors résidences/comptes démo et staff
uv run manage.py axes_reset                        # débloque un compte verrouillé par django-axes (local)
```

## Architecture

- **Une app Django = un module produit.** Apps existantes :
  - `core` : modèles `Residence`, `User` (custom : `residence`, `display_name`, `lot`, `is_demo`, préférences de notif), `ResidenceModule` ; auth ; recherche globale (`core/search.py`) ; middlewares ; PWA.
  - `incidents` : signalements avec cycle **Signalé → Pris en compte → En cours → Résolu**, `IncidentCategory`, `IncidentPhoto`, `IncidentUpdate` (journal).
  - `wall` : `Post` (types alerte/info/événement/entraide), commentaires, `PostPhoto`.
  - `directory` : carnet, **affiché sous le libellé « Information générale »** (l'URL reste `/carnet/`, le nom de route `directory_home` , ne pas renommer les routes).
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
- **Icônes = Lucide**, rendues via `<i data-lucide="nom"></i>` (jamais `{{ obj.icon }}` en texte brut). `lucide.createIcons()` est appelé dans `base.html`. Le champ `IncidentCategory.icon` contient un **nom d'icône Lucide**, pas un émoji. **Vérifier chaque nom sur lucide.dev/icons** avant usage, un nom inexistant s'affiche vide, sans erreur.
- **Contenu Markdown du mur** : rendu via le filtre `render_md` (`wall/templatetags/wall_extras.py`), qui fait `markdown` **puis** assainit avec **`nh3`**. **Toujours** afficher le contenu utilisateur via `render_md` (jamais `|safe` ni HTML brut) , c'est la protection XSS. Dépendances : `markdown`, `nh3`.
- Formatage : privilégier la sobriété, cohérence avec l'existant (palette neutre + accent émeraude, coins arrondis, cartes blanches, bordures fines).

## Tests

Le projet a une suite de tests réelle (`core/tests.py`, ~650 lignes) : isolation multi-tenant, 404 sur objets d'une autre résidence, notifications e-mail, mode démonstration, mode résidence unique.

```bash
uv run manage.py test            # suite complète
uv run manage.py test core       # une app seule
```

- **Toute nouvelle vue métier doit avoir son test d'isolation** : un utilisateur d'une autre résidence obtient un **404**, en GET **et** en POST.
- Les tests tournent sur **SQLite** en local. Vert ≠ garanti en Postgres (voir « Stack »).
- Ne jamais supprimer, commenter ou neutraliser un test existant pour faire passer une PR. Si un test devient faux, c'est une décision à assumer explicitement, pas un effet de bord.

## Sécurité (critique)

- **En-têtes de sécurité** posés par `core/middleware.py` → `SecurityHeadersMiddleware` (CSP, Permissions-Policy) + réglages `settings.py` (`X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY`, `SECURE_CONTENT_TYPE_NOSNIFF`, HSTS en prod).
- **CSP** : sources externes **autorisées** = `cdn.tailwindcss.com`, `unpkg.com` (`script-src`), `fonts.googleapis.com` (`style-src`), `fonts.gstatic.com` (`font-src`), et `img-src 'self' data: blob:`.
  → **Toute nouvelle ressource externe (CDN, image distante, script) DOIT être ajoutée à la CSP**, sinon elle est bloquée **en production** (souvent invisible en local). Préférer **héberger en local** dans `/static` plutôt qu'ajouter un CDN.
- **django-axes** (anti force brute sur la connexion) : `"axes"` dans `INSTALLED_APPS`, `"axes.middleware.AxesMiddleware"` dans les middlewares, et `"axes.backends.AxesBackend"` **en première position** de `AUTHENTICATION_BACKENDS` (avant `ModelBackend`) , l'ordre est significatif, ne pas le modifier. Template de blocage : `core/axes_lockout.html`. Ne jamais désactiver ni contourner. Compte verrouillé en local : `uv run manage.py axes_reset`.
- **Mode démonstration (`/demo/`, vue `core.demo`)** : connecte automatiquement un `User(is_demo=True)` rattaché à une `Residence(is_demo=True)`.
  - La **lecture seule est centralisée dans un middleware** (`core/middleware.py`) qui bloque toute méthode HTTP non sûre pour un utilisateur `is_demo`. **Ne pas ajouter de contrôle `is_demo` vue par vue**, et surtout **ne pas retirer ni court-circuiter ce middleware** : c'est la seule barrière, une nouvelle vue en écriture devient sinon exploitable publiquement.
  - Le **périmètre de navigation démo fonctionne par liste blanche de noms de routes** (`DEMO_PERIMETER_ROUTE_NAMES`, dans `core/middleware.py`) — jamais par comparaison de chaînes d'URL. Hors de cette liste, un utilisateur démo est **déconnecté**, reçoit un message en français (« Vous avez quitté la démonstration. ») et est renvoyé vers la page publique. ⚠️ **Piège coûteux : toute nouvelle page est HORS périmètre par défaut et ferme la session démo.** Si elle fait partie du tour de démonstration (module métier, compte, recherche, page publique), **son nom de route DOIT être ajouté à la liste blanche**, sinon le visiteur est éjecté au premier clic. `/admin/` est toujours exclue, indépendamment de la liste (vérifiée sur le namespace : `resolve('/admin/login/')` renvoie `url_name='login'`, identique à la route publique `login`). `/static/` et `/media/` sont exemptées par préfixe de chemin.
  - Le `login()` de la vue démo passe **explicitement** `backend="django.contrib.auth.backends.ModelBackend"`. C'est obligatoire : plusieurs backends sont configurés et il n'y a pas d'appel à `authenticate()`. **Retirer ce paramètre casse la démo** avec un `ValueError`.
  - La résidence de démonstration se régénère avec `uv run manage.py reset_demo`. Le flag `is_demo` sert aussi à exclure la démo des statistiques d'usage (`usage_report`) , ne pas le détourner pour autre chose.
- **Jamais de secret dans le code ni committé.** Les secrets vivent en **variables d'environnement Coolify**. **La liste de référence des variables est dans le `README.md`** , ne pas la dupliquer ici (source unique, sinon dérive). Trois d'entre elles ont un effet direct sur le comportement de l'app :
  - `ERROR_NOTIFY_EMAIL` : destinataire des alertes d'erreur 500 (défaut = `SIGNUP_NOTIFY_EMAIL`).
  - `OPEN_REGISTRATION` : `0` masque le parcours « créer une résidence » (mode résidence unique) , la route renvoie alors **404**.
  - `DONATE_URL` : lien de don (vide = masqué).
  `OPEN_REGISTRATION` et `DONATE_URL` sont exposés aux templates par `core/context_processors.py` (`open_registration`, `donate_url`) : **tout lien vers l'inscription ou le don doit passer par ces variables de contexte**, jamais en dur.
- Dans un README/doc, ne mettre que les **noms** des variables, jamais les valeurs.

## Médias / photos (fragile , suivre exactement)

Ce pipeline a déjà causé des pertes de fichiers. Règles impératives :

- **Pipeline obligatoire à tout point d'écriture de photo** : valider et ré-encoder via `core/photos.py` — `validate_photo(f)` (taille, extension, contenu réel) puis `prepare_photo(f)` (ré-encodage, suppression EXIF/GPS, redimensionnement). La fonction unique `save_photos(instance, files, limit=3)` (incidents et mur) enveloppe le tout et renvoie les messages d'erreur en français. **Jamais** `objects.create(image=f)` brut : les validators de champ ne s'exécutent pas via `objects.create()`, seule la vue admin (formulaire) les déclenche.
- **Formats acceptés** : JPG, PNG, WEBP, HEIC/HEIF. **HEIC → JPEG à l'enregistrement** (aucun navigateur ne décode le HEIC) : le nom transmis au champ porte l'extension du format réellement écrit (`photo.jpg`), jamais `.heic`.
- **Limite de taille** : 5 Mo (`core/validators.py`, appliquée sur le fichier reçu **avant** traitement).
- **Redimensionnement côté serveur** : plus grand côté ramené à 2000 px si dépassement (ratio conservé), dans `prepare_photo`. Aucun redimensionnement côté client (JS/canvas).
- **EXIF/GPS supprimés** : le ré-encodage ne recopie pas les métadonnées (orientation EXIF appliquée aux pixels avant suppression, pour ne pas stocker des photos à l'envers).
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
- Après déploiement, vérifier les logs Coolify (build vert, migrations `… OK`). C'est le **seul** endroit où l'on voit une migration s'appliquer réellement sur PostgreSQL.

## Workflow attendu

1. Créer une **branche** à partir de `main` à jour.
2. Développer, **commiter par lot** (un commit = un changement cohérent).
3. Tester en local : `uv run manage.py check`, `uv run manage.py makemigrations --check`, `uv run manage.py test`, **et tour des écrans à l'œil** (console F12 ouverte pour repérer les blocages CSP).
4. PR → merge dans `main` → déploiement auto → **re-tester en production** (surtout ce qui touche CSP, Service Worker, migrations, e-mails Brevo).

## Vérification (ne pas se fier au « c'est fait »)

- « Ça compile / le check passe » **ne veut pas dire** « c'est réussi visuellement ». Toujours **regarder le rendu**.
- « Les tests passent » ne veut pas dire « ça marche en production » : les tests tournent sur SQLite, la prod est sur PostgreSQL.
- Avant d'affirmer une exhaustivité (« plus aucune occurrence »), **le prouver avec `grep`**. Exemple pour les icônes en texte brut :
  ```bash
  grep -rn "\.icon" templates/    # toute ligne {{ ...icon }} sans data-lucide = bug
  ```
- Après une suppression de photo, **vérifier le disque** (`ls media/...`) que le fichier a bien disparu.
- Ne jamais déduire d'une absence de mention dans ce fichier une absence dans le code : **lire le code avant d'affirmer**.

## À NE PAS faire

- ❌ Utiliser `pip` (toujours `uv`).
- ❌ Merger avec `uv run manage.py test` rouge, ou supprimer un test pour le faire passer.
- ❌ Réimplémenter une fonctionnalité déjà présente sans avoir vérifié qu'elle n'existe pas (édition de posts/incidents, `render_md`, `upload_to` UUID, signaux de nettoyage, middleware démo… existent déjà).
- ❌ Supprimer des photos via `filter(...).delete()` en masse (contourne le signal → fichiers orphelins).
- ❌ Enregistrer une photo par `objects.create(image=f)` (ou `photo.image.save()`) sans passer par le pipeline `core/photos.py` (`save_photos` → `validate_photo` + `prepare_photo`) : la validation ne s'exécute pas via `objects.create()`, et le HEIC/EXIF/GPS/taille ne serait ni vérifié ni traité.
- ❌ Ajouter un CDN/ressource externe sans mettre à jour la CSP (`core/middleware.py`).
- ❌ Renommer les routes existantes (`directory_home`, etc.) , seul l'affichage change, pas les URLs.
- ❌ Afficher du contenu utilisateur sans `render_md` (risque XSS).
- ❌ Donner accès à l'admin Django au conseil syndical (le CS agit depuis l'app).
- ❌ Désactiver django-axes, ou changer l'ordre de `AUTHENTICATION_BACKENDS`.
- ❌ Retirer le middleware de lecture seule démo, ou le `backend=` explicite du `login()` de la vue démo.
- ❌ Coder un lien vers l'inscription ou le don en dur, sans passer par `open_registration` / `donate_url`.
- ❌ Committer un secret ou écrire une valeur secrète dans un fichier.