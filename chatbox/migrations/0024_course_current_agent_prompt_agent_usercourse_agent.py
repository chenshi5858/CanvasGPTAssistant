# Generated manually on 2026-03-16

import django.db.models.deletion
from django.db import migrations, models


def backfill_agent_fields(apps, schema_editor):
    Course = apps.get_model("chatbox", "Course")
    Prompt = apps.get_model("chatbox", "Prompt")
    UserCourse = apps.get_model("chatbox", "UserCourse")

    for course_id, current_agent_id in Course.objects.values_list("id", "current_agent_id").iterator():
        if current_agent_id is None:
            continue
        Prompt.objects.filter(course_id=course_id, agent_id__isnull=True).update(agent_id=current_agent_id)
        UserCourse.objects.filter(course_id=course_id, agent_id__isnull=True).update(agent_id=current_agent_id)


def clear_backfilled_agent_fields(apps, schema_editor):
    Prompt = apps.get_model("chatbox", "Prompt")
    UserCourse = apps.get_model("chatbox", "UserCourse")

    Prompt.objects.all().update(agent_id=None)
    UserCourse.objects.all().update(agent_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("chatbox", "0023_replace_promptsummary_with_coursesummary"),
    ]

    operations = [
        migrations.RenameField(
            model_name="course",
            old_name="agent_id",
            new_name="current_agent",
        ),
        migrations.AddField(
            model_name="prompt",
            name="agent",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prompts",
                to="chatbox.agent",
            ),
        ),
        migrations.AddField(
            model_name="usercourse",
            name="agent",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="user_courses",
                to="chatbox.agent",
            ),
        ),
        migrations.RemoveIndex(
            model_name="prompt",
            name="chatbox_pro_course__c0b6ff_idx",
        ),
        migrations.AddIndex(
            model_name="prompt",
            index=models.Index(fields=["course", "canvas_user", "agent", "created"], name="chatbox_pro_course__41f5c3_idx"),
        ),
        migrations.RunPython(backfill_agent_fields, clear_backfilled_agent_fields),
        migrations.AddConstraint(
            model_name="usercourse",
            constraint=models.UniqueConstraint(
                fields=("canvas_user", "course", "agent"),
                name="chatbox_usercourse_canvas_course_agent_uniq",
            ),
        ),
    ]
