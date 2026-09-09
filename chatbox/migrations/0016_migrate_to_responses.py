from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0015_remove_agent_course_id_course_agent_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agent',
            name='assistant_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='agent',
            name='instructions',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='agent',
            name='model',
            field=models.CharField(default='gpt-4.1-mini', max_length=255),
        ),
        migrations.AddField(
            model_name='agent',
            name='prompt_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.RemoveField(
            model_name='usercourse',
            name='thread_id',
        ),
        migrations.AddField(
            model_name='usercourse',
            name='conversation_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
