Analyse `git diff --staged` et crée un commit conventionnel.

Format : <type>(<scope>): <description>

Types : feat, fix, docs, style, refactor, test, chore
Scopes suggérés (cohérents avec les apps du projet) : core, incidents, wall, directory, deploy

Exemple :
feat(incidents): add photo cleanup on bulk delete
- Loop over objects individually to trigger post_delete signal
- Avoid orphaned files on QuerySet.delete()
