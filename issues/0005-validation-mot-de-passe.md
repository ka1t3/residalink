# Durcissement de la validation des mots de passe

## Problème

Aujourd'hui, `config/settings.py` ne déclare qu'**un seul** validateur de mot de
passe :

```python
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
]
```

Dès qu'un mot de passe fait 8 caractères, il est accepté — y compris `password`,
`12345678` ou `motdepasse`. C'est le point faible classique : un mot de passe
« correct » en nombre de caractères mais très courant n'a pas de valeur réelle
contre une attaque hors-ligne (hash volés — ex. fuite de base, dump, capture
d'un backup).

Le public cible (résidents peu à l'aise avec l'informatique) a besoin qu'on le
guide vers un mot de passe **mémorable mais pas trivial**, sans l'engager dans
une politique de complexité agressive (majuscule + chiffre + symbole), source
d'abandon et de post-it.

## Objectifs

1. Bloquer les mots de passe **trop communs** (top-20 000 mots de passe les
   plus utilisés, listés par Django).
2. **Zéro friction sur l'interface** : les 3 formulaires d'inscription /
   réinitialisation / changement de mot de passe affichent déjà les erreurs de
   champ (`field.errors`) — le simple ajout du validateur dans `settings.py`
   suffit, aucune modification de template.
3. **Aucun impact** sur le mode démo (compte démo créé via
   `set_unusable_password()`, pas de formulaire de mot de passe).

## Périmètre proposé

### Validateur ajouté

On s'appuie exclusivement sur les validateurs intégrés à Django
(`django.contrib.auth.password_validation.*`). Aucun code maison, aucune
dépendance.

| Validateur | Effet | Décision |
|---|---|---|
| `MinimumLengthValidator` (min 8) | déjà présent | ✅ **conservé tel quel** (longueur mini 8) |
| `CommonPasswordValidator` | bloque le top-20 000 mots de passe les plus utilisés (`password`, `12345678`, `motdepasse`, `toto1234`…) | ✅ **ajout** |
| `NumericPasswordValidator` | bloque les mots 100 % chiffres | ⛔ non retenu (voir « Hors périmètre ») |
| `UserAttributeSimilarityValidator` | bloque un mot trop semblable à l'e-mail / au nom | ⛔ non retenu (voir « Hors périmètre ») |

### Pourquoi `CommonPasswordValidator`, et pourquoi les autres non

- **`CommonPasswordValidator`** : haute valeur / faible friction. Un résident
  qui choisit une phrase mémorable (`ma-residence-bleue-42`, `coq-bleu-77`) ne
  tombe jamais dessus. Il ne bloque que ce qui est objectivement trivial
  (`password`, `12345678`, `motdepasse`, `toto1234`).
- **`NumericPasswordValidator` (non retenu)** : laisser un résident choisir un
  mot de passe entièrement numérique (ex. une date, un numéro) — c'est un choix
  assumé, on ne veut pas l'interdire ni le rendre confus.
- **`UserAttributeSimilarityValidator` (non retenu)** : refuserait un mot « trop
  semblable à l'e-mail » (ex. `marie.dupont` → `dupont2024`). Pour un public non
  technique, le message « trop semblable à l'e-mail » est contre-productif et
  générera de l'erreur. On préfère un mot simple mais non trivial.

### Impact concret

- `config/settings.py` : ajout de **1 entrée** dans `AUTH_PASSWORD_VALIDATORS`
  (2 lignes).
- Les formulaires Django standards qui en héritent automatiquement la **validation**
  : `JoinForm` (inscription, `UserCreationForm`) — `/rejoindre/`,
  `SetPasswordForm` (réinitialisation par e-mail) — `/reinitialiser/…`,
  `PasswordChangeForm` (changement depuis le profil) — `/profil/mot-de-passe/`.
- **Aucun changement de template** : les templates n'affichent pas `field.help_text`
  (le texte d'aide automatique Django n'est donc pas rendu, mais les **erreurs de
  rejet** s'affichent correctement). Afficher la liste des règles est un éventuel
  bonus ergonomique hors périmètre.
- **Aucune migration** : pas de changement de modèle.
- **Aucune dépendance** : le validateur est dans le core Django.

### Messages (traduction FR déjà fournie par Django)

- Erreur de rejet affichée sous le champ : « **Ce mot de passe est trop
  courant.** »
- Longueur insuffisante (inchangé) : « Ce mot de passe est trop court. Il doit
  contenir au minimum 8 caractères. »
- Le texte d'aide automatique de Django (liste des règles) n'est **pas** affiché
  par les templates actuels (le champ `password1` de `join.html` affiche une
  aide personnalisée « 8 caractères, ex. A3F2B1 », et les templates reset / changement
  n'affichent que label + champ + erreurs). Afficher cette liste est un éventuel
  bonus d'ergonomie hors périmètre.

## Fichiers touchés

- `config/settings.py` (`AUTH_PASSWORD_VALIDATORS` : 1 entrée ajoutée)
- `core/tests.py` (`PasswordValidatorTests` : mots courants refusés, mots
  mémorables acceptés, réinitialisation et changement couverts, démo non
  impactée)

## Implémentation (réalisée)

- `config/settings.py` : `CommonPasswordValidator` ajouté à
  `AUTH_PASSWORD_VALIDATORS` (2 lignes). `MinimumLengthValidator` (min 8)
  inchangé.
- `core/tests.py` : 7 tests (`PasswordValidatorTests`) — inscription refusée
  (mot courant, `12345678`, 7 caractères), inscription acceptée (mot
  mémorable), réinitialisation refusée (flux token → session → `set-password`
  de Django 6), changement refusé, `create_user` / `set_unusable_password`
  non validés (démo, bootstrap).
- Exemples vérifiés contre la liste réelle de Django : `password`,
  `12345678`, `motdepasse`, `1234567890`, `toto1234` bloqués ; `azerty1234`,
  `residence`, `bienvenue` non bloqués (hors top-20k).
- Message de rejet affiché : « Ce mot de passe est trop courant. »
- Total : 41 tests OK, `check` / `makemigrations --check` verts.

## Critères d'acceptation

- [x] `AUTH_PASSWORD_VALIDATORS` contient `MinimumLengthValidator` (8,
      inchangé) et `CommonPasswordValidator` ;
- [x] inscription (`/rejoindre/`) avec un mot du top-20 000
      (ex. `motdepasse` ou `password`) → **refusée** avec « Ce mot de passe est
      trop courant. » — pas de compte créé ;
- [x] inscription avec `12345678` (courant) → **refusée** (id. message) ;
- [x] inscription avec un mot de passe de 7 caractères → refusée (règle
      existante, non régressée) ;
- [x] inscription avec un mot de passe mémorable mais non courant
      (ex. `ma-residence-bleue-42`, `coq-bleu-77`) → **acceptée**, compte créé ;
- [x] réinitialisation de mot de passe (token, `SetPasswordForm`) avec un mot
      courant → refusée ;
- [x] changement de mot de passe (`/profil/mot-de-passe/`,
      `PasswordChangeForm`) avec un mot courant → refusé ;
- [x] le mode démo n'est pas impacté (connexion démo, `reset_demo`) ;
- [x] aucun template modifié (les erreurs de champ s'affichent déjà) ;
- [x] `uv run manage.py check` et `makemigrations --check` verts ;
- [x] tests : `core/tests.py::PasswordValidatorTests` + suite complète
      `uv run manage.py test` verte ;
- [x] tour des écrans : `/rejoindre/`, réinitialisation (lien e-mail),
      `/profil/mot-de-passe/` — les 3 affichent les erreurs, aucun blocage CSP.

## Hors périmètre

- `NumericPasswordValidator` : un mot de passe 100 % chiffres reste autorisé
  (choix assumé, pas de blocage ni de message ambigu pour le résident).
- `UserAttributeSimilarityValidator` : friction pour le public cible, message
  « trop semblable à l'e-mail » jugé contre-productif.
- Politique de **rotation** (âge maximal du mot de passe, historique des N
  derniers mots) : pas de besoin à cette échelle, et source de friction.
- Exigence de **complexité** (majuscule + chiffre + symbole) : on veut rester
  simple pour le public peu technique ; `CommonPassword` suffit à éliminer les
  mots vraiment faibles.
- Microcopy / message d'aide personnalisé : les messages et le texte d'aide
  fournis par Django (en français) sont suffisants.
- Renforcement de l'`invite_code` (`token_hex(4)`), auto-hébergement de Tailwind
  (CSP `unsafe-inline`), GDPR : issues distinctes déjà listées.