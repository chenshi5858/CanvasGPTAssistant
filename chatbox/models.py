from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

# Create your models here.


class Agent(models.Model):
    model = models.CharField(max_length=255, default="gpt-5-mini")
    instructions = models.TextField(null=True, blank=True)
    name = models.CharField(max_length=255, default="ASISTENTE UANDES")
    api_key = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='agents_created'
    )

    def __str__(self):
        return f"{self.name} ({self.id})"


class Course(models.Model):
    current_agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="Courses", default=1)
    canvas_id=models.IntegerField()
    title=models.TextField()
    created = models.DateTimeField(auto_now_add = True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='courses_created',
    )    
    def __str__(self):
        return self.title


class CourseClassSchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="class_schedules",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    active_from = models.DateField(null=True, blank=True)
    active_until = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("course__title", "weekday", "start_time")
        indexes = [
            models.Index(fields=["course", "weekday", "start_time", "end_time"]),
        ]

    def __str__(self):
        return (
            f"{self.course} - {self.get_weekday_display()} "
            f"{self.start_time:%H:%M}-{self.end_time:%H:%M}"
        )

    def clean(self):
        if self.start_time == self.end_time:
            raise ValidationError("Class schedule start and end time cannot be the same.")
        if self.active_from and self.active_until and self.active_from > self.active_until:
            raise ValidationError("active_from cannot be after active_until.")


class CanvasUser(models.Model):
    canvas_id=models.IntegerField()
    login=models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.login


class Category(models.Model):
    name=models.TextField()
    description = models.TextField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='categories_created',
        editable=False,  
    )    
    class Meta:
        verbose_name_plural = "Categories"
    def __str__(self):
        return self.name


class Prompt(models.Model):
    class InteractionType(models.TextChoices):
        ANSWER = "answer", "Answer"
        CLARIFICATION = "clarification", "Clarification"
        QUESTION = "question", "Question"
        OUT_OF_CONTEXT = "out_of_context", "Out of context"

    class AnswerCorrectness(models.TextChoices):
        CORRECT = "correct", "Correct"
        PARTIALLY_CORRECT = "partially_correct", "Partially correct"
        INCORRECT = "incorrect", "Incorrect"
        NOT_APPLICABLE = "not_applicable", "Not applicable"

    canvas_user = models.ForeignKey(CanvasUser, on_delete=models.CASCADE, related_name="prompts")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="prompts")
    agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        related_name="prompts",
        null=True,
        blank=True,
        default=None,
    )
    category = models.ForeignKey(Category, related_name="prompts", on_delete=models.SET_NULL, null=True, blank=True, default=None)
    prompt_text = models.TextField()
    prompt_answer = models.TextField()
    interaction_type = models.CharField(
        max_length=32,
        choices=InteractionType.choices,
        null=True,
        blank=True,
    )
    answer_correctness = models.CharField(
        max_length=32,
        choices=AnswerCorrectness.choices,
        null=True,
        blank=True,
    )
    interaction_analyzed_at = models.DateTimeField(null=True, blank=True)
    interaction_analysis_error = models.TextField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["course", "canvas_user", "agent", "created"]),
            models.Index(fields=["interaction_analyzed_at"]),
        ]

    def __str__(self):
        return f"{self.canvas_user} - {self.course} - {self.prompt_text[:30]}"


class CourseSummary(Course):
    class Meta:
        proxy = True
        verbose_name = "Course Summary"
        verbose_name_plural = "Course Summaries"

    
class UserCourse(models.Model):
    canvas_user = models.ForeignKey(CanvasUser, on_delete=models.CASCADE, related_name="user_courses")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="user_courses")
    agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        related_name="user_courses",
        null=True,
        blank=True,
        default=None,
    )
    conversation_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["canvas_user", "course", "agent"],
                name="chatbox_usercourse_canvas_course_agent_uniq",
            )
        ]


class UserCourseInteractionSummary(UserCourse):
    class Meta:
        proxy = True
        verbose_name = "Student Interaction"
        verbose_name_plural = "Student Interactions"
