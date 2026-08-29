# Contribuer à Residalink

Merci de l'intérêt que vous portez au projet ! Cette page explique comment aider à construire **Residalink**, que ce soit par du code, des idées, des retours d'usage ou de la documentation. **Toute contribution compte**, et il n'est pas nécessaire d'être un développeur chevronné pour être utile.

> **Residalink est un projet bénévole, gratuit et open source.** Il n'y a rien à vendre : le seul objectif est que l'outil serve vraiment à des résidences. Si vous souhaitez aider autrement que par du temps, vous pouvez [soutenir le projet financièrement](https://liberapay.com/residalink/donate).

---

## Pour commencer : utilisez l'outil

Avant tout, le plus utile est de **vous en servir**. Rendez-vous sur **[residalink.com](https://residalink.com)**, créez (ou demandez) une résidence, signalez un incident, publiez sur le mur, remplissez le carnet. Rien ne remplace le fait de vivre l'expérience d'un vrai utilisateur.

En l'utilisant, vous repérerez naturellement ce qui est confus, ce qui manque, ou ce qui pourrait être plus simple. **C'est exactement ce qu'on cherche.**

---

## La façon la plus simple de contribuer : les retours

**Ouvrez une [issue](../../issues/new) pour tout ce qui vous interpelle** : un bug, une maladresse d'ergonomie, une fonctionnalité qui vous manquerait, ou simplement une question. Aucune contribution technique n'est requise — un bon retour d'usage vaut souvent plus qu'une ligne de code.

Sont particulièrement précieux :

- **Les bugs** : décrivez ce que vous faisiez, ce que vous attendiez, et ce qui s'est passé.
- **Les frictions d'usage** : « je ne comprenais pas où cliquer », « ce mot ne me parle pas »… La simplicité est la priorité n°1 du projet.
- **Les retours de terrain** : votre résidence utilise l'outil ? Racontez ce qui marche et ce qui coince. C'est le signal le plus utile qui soit.
- **Les idées** : une fonctionnalité qui rendrait service à votre copropriété ? Proposez-la, en expliquant le **besoin concret** derrière.

> **Un principe du projet : on ne construit pas une fonctionnalité tant qu'un besoin réel n'est pas confirmé.** Décrire *pourquoi* vous voulez quelque chose est donc plus utile que décrire *quoi*.

---

## Contribuer au code

Envie de mettre les mains dans le cambouis ? Voici comment.

### Choisir sur quoi travailler

- Jetez un œil à la **[liste des issues](../../issues)**. Si rien ne vous inspire, l'important est de choisir **ce qui vous intéresse vraiment**.
- Les issues étiquetées **[`good first issue`](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)** sont idéales pour se familiariser avec le projet.
- Avant de vous lancer sur quelque chose de conséquent, **ouvrez ou commentez une issue** pour en discuter — ça évite de dupliquer le travail ou de partir dans une direction non souhaitée.

### Mettre en place l'environnement

Le guide complet d'installation est dans le **[README](README.md#lancer-le-projet-en-local)**. En résumé :

```bash
uv sync
uv run manage.py migrate
uv run manage.py bootstrap "Résidence de démo"
uv run manage.py createsuperuser
uv run manage.py runserver
```

> **Utilisez `uv`, jamais `pip`.** Le projet est verrouillé sur `uv.lock`.

### Lire les conventions du projet

Le fichier **[`AGENTS.MD`](AGENTS.MD)** à la racine résume l'architecture, les conventions et les **pièges à éviter** (sécurité, CSP, migrations, gestion des médias). Lisez-le avant de coder — il vous fera gagner beaucoup de temps, et il s'applique aussi bien à vous qu'aux agents de code.

### Le circuit d'une contribution

1. **Forkez** le dépôt et créez une **branche** dédiée à partir de `main`.
2. Développez, en **testant en local** au fur et à mesure.
3. Avant de proposer vos changements, vérifiez :
   ```bash
   uv run manage.py check
   uv run manage.py makemigrations --check   # doit dire « No changes detected »
   ```
4. **Testez visuellement** ce que vous avez modifié (le `check` valide que ça compile, pas que ça s'affiche bien).
5. Ouvrez une **Pull Request** vers `main`, en décrivant clairement le *pourquoi* et le *comment*.

### Quelques règles de qualité

- **Interface en français** — c'est la langue des utilisateurs.
- **Sécurité d'abord** : restreignez toujours les données à la résidence de l'utilisateur (`residence_id`), assainissez le contenu utilisateur, ne committez **jamais** de secret.
- **Sobriété** : restez cohérent avec l'existant (palette neutre + accent émeraude, interface épurée). La simplicité passe avant la richesse.
- **Prouvez plutôt qu'affirmez** : ne concluez pas « c'est corrigé partout » sans l'avoir vérifié (un `grep` vaut mieux qu'une intuition).

---

## Traductions

Residalink est aujourd'hui en français. Si vous souhaitez le rendre disponible dans une autre langue, **ouvrez une issue** pour qu'on en discute et qu'on prépare le terrain ensemble.

---

## Documentation

Améliorer le README, ce guide, ou les commentaires du code est une contribution à part entière — souvent la plus utile pour les prochains arrivants. N'hésitez pas.

---

## Une question, une idée en germe ?

Pas besoin d'une contribution finalisée pour participer. Si vous avez une intuition, une question, ou une envie de discuter d'une direction, **[ouvrez une issue](../../issues/new)** — même informelle. On construit cet outil ensemble, à l'écoute des vrais besoins.

**Merci de faire partie de l'aventure. **
