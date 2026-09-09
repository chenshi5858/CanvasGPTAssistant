from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from chatbox.models import (
    Course,
    Agent,
    Category,
    Prompt,
    CourseSummary,
    UserCourse,
    UserCourseInteractionSummary,
    CourseClassSchedule,
)

class Command(BaseCommand):

    def handle(self, *args, **options):
        try:
            group, created = Group.objects.get_or_create(name = 'Teachers')
            if created:
                self.stdout.write(self.style.SUCCESS('Successfully created "Teachers" group'))
            else:
                self.stdout.write(self.style.WARNING('"Teachers" group already exists'))
            
            course_ct = ContentType.objects.get_for_model(Course)
            course_schedule_ct = ContentType.objects.get_for_model(CourseClassSchedule)
            agent_ct = ContentType.objects.get_for_model(Agent)
            category_ct = ContentType.objects.get_for_model(Category)
            prompt_ct = ContentType.objects.get_for_model(Prompt)
            course_summary_ct = ContentType.objects.get_for_model(
                CourseSummary,
                for_concrete_model=False,
            )
            user_course_ct = ContentType.objects.get_for_model(UserCourse)
            interaction_summary_ct = ContentType.objects.get_for_model(
                UserCourseInteractionSummary,
                for_concrete_model=False,
            )

            permissions = [
                Permission.objects.get(codename='add_course', content_type=course_ct),
                Permission.objects.get(codename='change_course', content_type=course_ct),
                Permission.objects.get(codename='delete_course', content_type=course_ct),
                Permission.objects.get(codename='view_courseclassschedule', content_type=course_schedule_ct),
                Permission.objects.get(codename='add_courseclassschedule', content_type=course_schedule_ct),
                Permission.objects.get(codename='change_courseclassschedule', content_type=course_schedule_ct),
                Permission.objects.get(codename='delete_courseclassschedule', content_type=course_schedule_ct),
                Permission.objects.get(codename='add_agent', content_type=agent_ct),
                Permission.objects.get(codename='change_agent', content_type=agent_ct),
                Permission.objects.get(codename='delete_agent', content_type=agent_ct),
                Permission.objects.get(codename='add_category', content_type=category_ct),
                Permission.objects.get(codename='change_category', content_type=category_ct),
                Permission.objects.get(codename='delete_category', content_type=category_ct),
                Permission.objects.get(codename='view_prompt', content_type=prompt_ct),
                Permission.objects.get(codename='view_coursesummary', content_type=course_summary_ct),
                Permission.objects.get(codename='change_coursesummary', content_type=course_summary_ct),
                Permission.objects.get(codename='view_usercourse', content_type=user_course_ct),
                Permission.objects.get(
                    codename='view_usercourseinteractionsummary',
                    content_type=interaction_summary_ct,
                ),
            ]

            group.permissions.set(permissions)

            self.stdout.write(self.style.SUCCESS('Successfully assigned permissions to "Teachers" group'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating group or assigning permissions: {e}'))
