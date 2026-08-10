from django.db import migrations

# Correspondance émoji -> nom Lucide. À VÉRIFIER sur lucide.dev/icons.
EMOJI_TO_LUCIDE = {
    "🛗": "arrow-up-down",   # Lucide n'a pas d'"elevator" — à confirmer
    "💧": "droplet",         # existe
    "💡": "lightbulb",       # existe
    "🚪": "door-open",       # existe
    "🧹": "spray-can",       # à confirmer (sinon "sparkles")
    "🔧": "wrench",          # existe
}


def emojis_to_lucide(apps, schema_editor):
    IncidentCategory = apps.get_model("incidents", "IncidentCategory")
    for cat in IncidentCategory.objects.all():
        if cat.icon in EMOJI_TO_LUCIDE:
            cat.icon = EMOJI_TO_LUCIDE[cat.icon]
            cat.save(update_fields=["icon"])


def noop(apps, schema_editor):
    # Irréversible proprement : on ne rétablit pas les émojis. Migration avant non bloquée.
    pass


class Migration(migrations.Migration):
    dependencies = [("incidents", "0004_alter_incidentcategory_icon")]
    operations = [migrations.RunPython(emojis_to_lucide, noop)]