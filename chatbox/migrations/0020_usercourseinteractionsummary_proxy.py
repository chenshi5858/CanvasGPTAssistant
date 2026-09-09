from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0019_prompt_interaction_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserCourseInteractionSummary',
            fields=[],
            options={
                'verbose_name': 'Student Interaction',
                'verbose_name_plural': 'Student Interactions',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('chatbox.usercourse',),
        ),
    ]
