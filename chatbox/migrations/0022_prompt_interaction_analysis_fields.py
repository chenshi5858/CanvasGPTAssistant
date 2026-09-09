from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chatbox', '0021_rename_chatbox_prom_course__95fd7e_idx_chatbox_pro_course__c0b6ff_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='prompt',
            name='answer_correctness',
            field=models.CharField(blank=True, choices=[('correct', 'Correct'), ('partially_correct', 'Partially correct'), ('incorrect', 'Incorrect'), ('not_applicable', 'Not applicable')], max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='prompt',
            name='interaction_analysis_error',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='prompt',
            name='interaction_analyzed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='prompt',
            name='interaction_type',
            field=models.CharField(blank=True, choices=[('answer', 'Answer'), ('clarification', 'Clarification'), ('question', 'Question'), ('out_of_context', 'Out of context')], max_length=32, null=True),
        ),
        migrations.AddIndex(
            model_name='prompt',
            index=models.Index(fields=['interaction_analyzed_at'], name='chatbox_prom_interac_8d95f8_idx'),
        ),
    ]
