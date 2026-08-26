from django.db import migrations


def create_conseil_syndical_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="conseil_syndical")


def noop(apps, schema_editor):
    # Ne supprime pas le groupe au rollback : il peut déjà contenir des membres.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_residencemodule_module'),
    ]

    operations = [
        migrations.RunPython(create_conseil_syndical_group, noop),
    ]
