from django.db import migrations, models
import uuid


def seed_coordination_sequence(apps, schema_editor):
    CoordinationActivity = apps.get_model('coordination', 'CoordinationActivity')
    ActivityCodeSequence = apps.get_model('coordination', 'ActivityCodeSequence')
    prefix = 'COO'
    last_number = 0
    for code in CoordinationActivity.objects.filter(code__startswith=prefix).values_list('code', flat=True):
        suffix = code[len(prefix):]
        if suffix.isdigit():
            last_number = max(last_number, int(suffix))
    ActivityCodeSequence.objects.get_or_create(
        prefix=prefix,
        defaults={'id': uuid.uuid4(), 'last_number': last_number},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('coordination', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityCodeSequence',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('prefix', models.CharField(max_length=16, unique=True)),
                ('last_number', models.PositiveIntegerField(default=0)),
            ],
            options={
                'db_table': 'tblCoordinationActivityCodeSequence',
            },
        ),
        migrations.RunPython(seed_coordination_sequence, migrations.RunPython.noop),
    ]
