from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0022_prompt_interaction_analysis_fields'),
    ]

    operations = [
        migrations.DeleteModel(
            name='PromptSummary',
        ),
        migrations.CreateModel(
            name='CourseSummary',
            fields=[],
            options={
                'verbose_name': 'Course Summary',
                'verbose_name_plural': 'Course Summaries',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('chatbox.course',),
        ),
    ]
