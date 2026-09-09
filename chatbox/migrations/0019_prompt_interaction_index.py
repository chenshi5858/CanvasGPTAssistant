from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0018_remove_agent_prompt_id'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='prompt',
            index=models.Index(fields=['course', 'canvas_user', 'created'], name='chatbox_prom_course__95fd7e_idx'),
        ),
    ]
