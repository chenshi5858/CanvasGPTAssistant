from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0016_migrate_to_responses'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agent',
            name='assistant_id',
        ),
    ]
