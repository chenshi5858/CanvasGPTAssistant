import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from chatbox.models import Agent, CanvasUser, Course, Prompt, UserCourse


class Command(BaseCommand):
    help = (
        "Crea datos demo para probar interacciones: 2 cursos, 10 estudiantes por curso "
        "y prompts aleatorios por estudiante."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--teacher",
            type=str,
            default=None,
            help="Username del profesor de Django a asignar como created_by.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Semilla para generar datos aleatorios reproducibles.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina datos demo previos antes de crear nuevos.",
        )

    def handle(self, *args, **options):
        seed = options["seed"]
        teacher_username = options["teacher"]
        clear = options["clear"]
        random.seed(seed)

        teacher = self._resolve_teacher(teacher_username)

        if clear:
            self._clear_demo_data()

        prompt_templates = [
            "No entiendo {topic}, ¿me lo puedes explicar con un ejemplo simple?",
            "¿Cuál es la diferencia entre {topic} y {alt_topic}?",
            "Dame un resumen corto sobre {topic}.",
            "¿Cómo aplico {topic} en un caso real de clase?",
            "¿Qué errores comunes hay al estudiar {topic}?",
        ]
        answer_templates = [
            "Claro. Empecemos por lo esencial de {topic}: {detail}.",
            "Buena pregunta. La idea central de {topic} es {detail}.",
            "Una forma práctica de verlo es así: {detail}.",
            "Te propongo este enfoque para {topic}: {detail}.",
            "En términos simples, {topic} se entiende mejor cuando {detail}.",
        ]
        topics = [
            "derivadas",
            "integrales",
            "probabilidad condicional",
            "matrices",
            "estadística descriptiva",
            "álgebra lineal",
            "límites",
            "regresión lineal",
        ]
        details = [
            "relacionas concepto, fórmula y aplicación",
            "separa definición de intuición",
            "usas un ejemplo numérico concreto",
            "identificas supuestos antes de resolver",
            "conectas la teoría con ejercicios guiados",
        ]

        created_courses = 0
        created_users = 0
        created_user_courses = 0
        prompts_to_create = []

        with transaction.atomic():
            for course_index in range(1, 3):
                agent, _ = Agent.objects.get_or_create(
                    name=f"Demo Agent {course_index}",
                    defaults={
                        "model": "gpt-5-mini",
                        "instructions": (
                            "Eres un asistente docente. Responde en español, "
                            "con claridad, pasos breves y ejemplos simples."
                        ),
                        "api_key": "",
                        "created_by": teacher,
                    },
                )
                if teacher and agent.created_by_id is None:
                    agent.created_by = teacher
                    agent.save(update_fields=["created_by"])

                course, course_created = Course.objects.get_or_create(
                    canvas_id=900000 + course_index,
                    defaults={
                        "title": f"Demo Course {course_index}",
                        "current_agent": agent,
                        "created_by": teacher,
                    },
                )
                if course_created:
                    created_courses += 1

                if course.current_agent_id != agent.id:
                    course.current_agent = agent
                    course.save(update_fields=["current_agent"])
                if teacher and course.created_by_id is None:
                    course.created_by = teacher
                    course.save(update_fields=["created_by"])

                for user_index in range(1, 11):
                    login = f"demo_student_c{course_index}_{user_index:02d}"
                    canvas_user, user_created = CanvasUser.objects.get_or_create(
                        canvas_id=course_index * 10000 + user_index,
                        defaults={"login": login},
                    )
                    if user_created:
                        created_users += 1
                    elif canvas_user.login != login and canvas_user.login.startswith("demo_student_"):
                        canvas_user.login = login
                        canvas_user.save(update_fields=["login"])

                    user_course, uc_created = UserCourse.objects.get_or_create(
                        canvas_user=canvas_user,
                        course=course,
                        agent=agent,
                        defaults={"conversation_id": f"demo-conv-{course_index}-{user_index}"},
                    )
                    if uc_created:
                        created_user_courses += 1
                    elif not user_course.conversation_id:
                        user_course.conversation_id = f"demo-conv-{course_index}-{user_index}"
                        user_course.agent = agent
                        user_course.save(update_fields=["conversation_id", "agent"])

                    prompts_count = random.randint(3, 8)
                    prompt_time = timezone.now() - timedelta(
                        days=random.randint(0, 21),
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                    )

                    for _ in range(prompts_count):
                        topic = random.choice(topics)
                        alt_topic = random.choice([t for t in topics if t != topic])
                        detail = random.choice(details)
                        user_prompt = random.choice(prompt_templates).format(
                            topic=topic,
                            alt_topic=alt_topic,
                        )
                        ai_answer = random.choice(answer_templates).format(
                            topic=topic,
                            detail=detail,
                        )

                        prompt_time += timedelta(minutes=random.randint(5, 150))
                        prompts_to_create.append(
                            Prompt(
                                canvas_user=canvas_user,
                                course=course,
                                agent=agent,
                                prompt_text=user_prompt,
                                prompt_answer=ai_answer,
                                created=prompt_time,
                            )
                        )

            Prompt.objects.bulk_create(prompts_to_create, batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(
                "Datos demo creados. "
                f"Cursos nuevos: {created_courses}, "
                f"Usuarios nuevos: {created_users}, "
                f"UserCourse nuevos: {created_user_courses}, "
                f"Prompts creados: {len(prompts_to_create)}."
            )
        )

    def _resolve_teacher(self, teacher_username):
        User = get_user_model()
        if teacher_username:
            try:
                return User.objects.get(username=teacher_username)
            except User.DoesNotExist as exc:
                raise CommandError(f"No existe el usuario '{teacher_username}'.") from exc

        teacher_group = Group.objects.filter(name="Teachers").first()
        if teacher_group:
            teacher = teacher_group.user_set.filter(is_staff=True).order_by("id").first()
            if teacher:
                return teacher

        return User.objects.filter(is_staff=True).order_by("id").first()

    def _clear_demo_data(self):
        demo_courses = Course.objects.filter(title__startswith="Demo Course ")
        demo_course_ids = list(demo_courses.values_list("id", flat=True))
        if not demo_course_ids:
            return

        Prompt.objects.filter(course_id__in=demo_course_ids).delete()
        UserCourse.objects.filter(course_id__in=demo_course_ids).delete()
        demo_courses.delete()
        CanvasUser.objects.filter(login__startswith="demo_student_").delete()
        Agent.objects.filter(name__startswith="Demo Agent ").delete()
