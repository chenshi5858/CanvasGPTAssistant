from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0017_remove_agent_assistant_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agent',
            name='prompt_id',
        ),
    ]
