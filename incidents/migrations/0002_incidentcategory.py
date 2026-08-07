from django.db import migrations, models
import django.db.models.deletion

DEFAULTS = [
    ("ascenseur", "Ascenseur", "🛗", 1),
    ("fuite", "Fuite d'eau", "💧", 2),
    ("eclairage", "Éclairage", "💡", 3),
    ("portail", "Portail / porte", "🚪", 4),
    ("proprete", "Propreté", "🧹", 5),
    ("autre", "Autre", "🔧", 6),
]


def seed_and_map(apps, schema_editor):
    IncidentCategory = apps.get_model("incidents", "IncidentCategory")
    Incident = apps.get_model("incidents", "Incident")
    by_code = {}
    for code, name, icon, order in DEFAULTS:
        cat, _ = IncidentCategory.objects.get_or_create(name=name, defaults={"icon": icon, "order": order})
        by_code[code] = cat
    for incident in Incident.objects.all():
        incident.category_fk = by_code.get(incident.category, by_code["autre"])
        incident.save(update_fields=["category_fk"])


class Migration(migrations.Migration):
    dependencies = [("incidents", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="IncidentCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=60, unique=True, verbose_name="Nom")),
                ("icon", models.CharField(default="🔧", max_length=8, verbose_name="Icône (émoji)")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="Ordre d'affichage")),
            ],
            options={"ordering": ["order", "name"], "verbose_name": "Catégorie d'incident",
                     "verbose_name_plural": "Catégories d'incident"},
        ),
        migrations.AddField(
            model_name="incident", name="category_fk",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="incidents", to="incidents.incidentcategory"),
        ),
        migrations.RunPython(seed_and_map, migrations.RunPython.noop),
        migrations.RemoveField(model_name="incident", name="category"),
        migrations.RenameField(model_name="incident", old_name="category_fk", new_name="category"),
        migrations.AlterField(
            model_name="incident", name="category",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incidents",
                                    to="incidents.incidentcategory", verbose_name="Catégorie"),
        ),
    ]
