# Mode résidence unique : désactiver les pages SaaS publiques

## Problème

En déploiement **résidence unique** (l'opérateur installe Residalink pour son propre
immeuble), le parcours légitime d'un résident est :

```
/connexion/  (déjà inscrit)   ou   /rejoindre/  (code d'invitation)
```

Mais le site public expose aujourd'hui le parcours **SaaS multi-résidences** :

- La landing page présente un formulaire **« Créer l'espace de ma résidence »**
  (`templates/landing.html`, ancre `#creer`) — absurde pour un résident qui a
  déjà sa résidence.
- `/demande-residence/` reste actif : chaque soumission valide envoie un e-mail à
  l'opérateur (`SIGNUP_NOTIFY_EMAIL`). En résidence unique, c'est du bruit permanent
  (visiteurs perdus, bots qui contournent l'anti-spam, etc.).
- Le bandeau « Explorer la démonstration » + `/demo/` n'a pas de sens : il n'y a
  pas de résidence démo à présenter à des voisins qui viennent pour leur immeuble.

Conséquence : la page d'atterrissage, premier contact avec l'outil, est incohérente
avec le contexte réel, et l'opérateur reçoit des demandes de création qu'il ne
voudra jamais traiter.

## Objectifs

1. Un réglage unique (`OPEN_REGISTRATION`) pour basculer entre les deux modes,
   sans code mort ni branchement par résidence.
2. En mode résidence unique : la landing pointe vers **`/rejoindre/`**, les
   parcours SaaS disparaissent proprement (**404**, pas de message qui confirme
   leur existence), la démo est masquée.
3. Le comportement SaaS actuel (par défaut) reste strictement inchangé.

## Périmètre proposé

### Réglage

- Nouvelle variable d'environnement **`OPEN_REGISTRATION`** (bool, défaut `True`
  = comportement SaaS actuel). Documentée dans le README (nom seulement, jamais de
  valeur sensible).
- `config/settings.py` : `OPEN_REGISTRATION = os.environ.get("OPEN_REGISTRATION", "1") == "1"`.

### Comportement en mode résidence unique (`OPEN_REGISTRATION = False`)

| Surface | Comportement |
|---|---|
| `home` / landing (visiteur non connecté) | Section « Créer ma résidence » masquée (formulaire + bandeau `?envoye=1` + ancre `?creer` + bandeau démo) ; CTA principal « **Rejoindre ma résidence avec un code** » vers `/rejoindre/` |
| `/demande-residence/` (GET ou POST) | **404** (`raise Http404` dans la vue — la route reste déclarée, aucune URL à renommer) |
| Bande « Explorer la démonstration » | Masquée sur la landing |
| `/rejoindre/`, `/connexion/`, `/contact/`, `/confidentialite/`, `/mentions-legales/` | Inchangés (le contact reste utile : résident perdu, e-mail changé…) |
| Session démo (`DemoReadOnlyMiddleware`) | Inchangée ; `residence_request` dans `DEMO_ALLOWED_ROUTE_NAMES` devient inopérant en 404, pas d'impact |

### Comportement en mode SaaS (défaut, `OPEN_REGISTRATION = True`)

- Rien ne change : formulaire de création visible, `/demande-residence/` fonctionnel,
  bandeau démo affiché. Les tests existants de la landing restent verts.

## Fichiers touchés

- `config/settings.py` (réglage + variable d'environnement)
- `core/views.py` (`residence_request` : 404 si désactivé ; contexte `home`)
- `templates/landing.html` (sections conditionnelles)
- `core/tests.py` (nouvelle classe de tests `OpenRegistrationTests`)
- `README.md` (variable d'environnement documentée)

## Critères d'acceptation

- [x] `OPEN_REGISTRATION=True` (défaut) : landing avec formulaire « Créer ma
      résidence », `/demande-residence/` fonctionnel, bandeau démo visible —
      aucun test existant cassé ;
- [x] `OPEN_REGISTRATION=False` : la landing d'un visiteur ne contient ni
      formulaire de création, ni bandeau démo, et contient un lien vers
      `/rejoindre/` ;
- [x] `OPEN_REGISTRATION=False` : `GET /demande-residence/` → 404 ;
      `POST /demande-residence/` (avec honeypot/ts valides) → 404 **et aucun e-mail** ;
- [x] `OPEN_REGISTRATION=False` : `/rejoindre/` fonctionne de bout en bout
      (inscription avec code, premier inscrit → CS) ;
- [x] `OPEN_REGISTRATION=False` : `/connexion/`, `/contact/`, `/confidentialite/`
      → 200 ;
- [x] en session démo, aucun écran ne casse (la landing reste consultable) ;
- [x] `uv run manage.py check` et `makemigrations --check` verts ;
- [x] tests : 6 tests (`OpenRegistrationTests`) + suite complète : 40 tests OK ;
- [x] tour des écrans : landing non connectée dans les deux modes, `/rejoindre/`
      dans le mode résidence unique.

## Implémentation (réalisée)

- `config/settings.py` : `OPEN_REGISTRATION = os.environ.get("OPEN_REGISTRATION", "1") == "1"`
  + context processor enregistré.
- `core/context_processors.py` : `open_registration(request)` →
  `{"open_registration": settings.OPEN_REGISTRATION}` (disponible sur toutes les
  pages, y compris la bande démo de `base.html`).
- `core/views.py::residence_request` : `raise Http404` en tête si
  `not settings.OPEN_REGISTRATION` (toutes méthodes) ; `@require_POST` retiré
  (remplacé par `HttpResponseNotAllowed(["POST"])` manuel pour préserver le 405
  en mode SaaS et laisser passer le 404 fermé pour un GET).
- `templates/landing.html` :
  - **hero CTA** : `Créer ma résidence` + `Voir la démonstration` (SaaS) →
    `Rejoindre ma résidence` (fermé) ;
  - **header nav** : bouton `Créer ma résidence` → `#creer` (SaaS) →
    `Rejoindre ma résidence` → `/rejoindre/` (fermé) ;
  - **section `#creer`** : formulaire (SaaS) → carte `Rejoindre avec mon code
    d'invitation` (fermé), titre et sous-titre conditionnels ;
  - **bande humaine** : masquée en mode fermé.
- `templates/base.html` : bouton `Créer ma résidence` de la bande démo masqué
  en mode fermé (`Retour à l'accueil` conservé).
- `core/tests.py` : `OpenRegistrationTests` (6 tests).

## Hors périmètre

- Personnaliser le hero de la landing avec le nom de la résidence
  (améliorations possibles : « Bienvenue à la résidence X » quand une seule
  résidence non-démo existe) — issue séparée.
- Désactiver `/demo/` lui-même (la route reste, seulement masquée).
- Désactivation de `/contact/` (conservé : c'est le canal « résident perdu »).