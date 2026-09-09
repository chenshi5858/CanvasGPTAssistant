from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.template import loader, Context
from openai import OpenAI
from django.conf import settings
import json
import time
from django.views.decorators.csrf import csrf_exempt
from pylti1p3.message_launch import MessageLaunch
from pylti1p3.tool_config import ToolConfJsonFile
from oauthlib.oauth1 import RequestValidator, SignatureOnlyEndpoint
import logging
from django.views.decorators.clickjacking import xframe_options_exempt
from chatbox.models import CanvasUser, Course, Prompt, Agent, UserCourse
from django.views.generic import ListView 
from django.db import transaction
from chatbox.utils import render_markdown_with_latex, extract_response_text
import logging
from datetime import datetime



logger = logging.getLogger(__name__)
ANON_CHAT_SESSION_KEY = "anonymous_chat_state"

# openai.api_key = settings.OPENAI_API_KEY

consumer_key = settings.LTI_CONSUMER_KEY
shared_secret = settings.LTI_SHARED_SECRET

#client = OpenAI(api_key = settings.OPENAI_API_KEY)


def _get_anonymous_chat_state(request, agent_id):
    state = request.session.get(ANON_CHAT_SESSION_KEY, {})
    agent_state = state.get(str(agent_id), {})
    return {
        "conversation_id": agent_state.get("conversation_id"),
        "messages": agent_state.get("messages", []),
    }


def _save_anonymous_chat_state(
    request,
    agent_id,
    conversation_id=None,
    message=None,
    reset=False,
):
    state = request.session.get(ANON_CHAT_SESSION_KEY, {})
    agent_key = str(agent_id)

    if reset:
        state.pop(agent_key, None)
    else:
        agent_state = state.get(agent_key, {"messages": []})
        if conversation_id is not None:
            agent_state["conversation_id"] = conversation_id
        if message:
            agent_state.setdefault("messages", []).append(message)
        state[agent_key] = agent_state

    request.session[ANON_CHAT_SESSION_KEY] = state
    request.session.modified = True

def chatbox(request, agent_id):
    agent = Agent.objects.get(id=agent_id)
    if agent is None:
        agent = Agent.objects.first()
    anonymous_state = _get_anonymous_chat_state(request, agent.id)
    template = loader.get_template('chatgpt.html')
    context = {
        "agent_id": agent.id,
        "course_title": "Open",
        "messages": anonymous_state["messages"],
        "agent_name": agent.name,
        "canvas_user": '',
        "course": '',
        "login": '',
    }

    return HttpResponse(template.render(context))


@csrf_exempt
def chatgpt_response(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_message = data.get("message")
        canvas_user_id = data.get("canvas_user")
        agent_pk = data.get("agent")

        if canvas_user_id and len(canvas_user_id) > 0:
            course_id = int(data.get("course"))
            course = Course.objects.get(canvas_id = course_id)
            agent = course.current_agent
        else:
            agent = Agent.objects.get(id=agent_pk)

        if not agent.api_key:
            return JsonResponse({"error": "API key not configured for this agent."}, status=400)
        try:
            client = OpenAI(api_key=agent.api_key)

            conversation_id = None
            if canvas_user_id and len(canvas_user_id) > 0:
                user_login = data.get("login")
                canvas_user, created_user = CanvasUser.objects.get_or_create(
                    canvas_id = canvas_user_id,
                    defaults = {"login": user_login}
                )
                try:
                    user_course = UserCourse.objects.get(
                        canvas_user=canvas_user,
                        course=course,
                        agent=agent,
                    )
                    conversation_id = user_course.conversation_id
                except UserCourse.DoesNotExist:
                    with transaction.atomic():
                        conversation = client.conversations.create()
                        conversation_id = conversation.id

                        user_course = UserCourse.objects.create(
                            canvas_user=canvas_user,
                            course=course,
                            agent=agent,
                            conversation_id=conversation_id,
                        )
                if not conversation_id:
                    conversation = client.conversations.create()
                    conversation_id = conversation.id
                    user_course.conversation_id = conversation_id
                    user_course.agent = agent
                    user_course.save(update_fields=["conversation_id", "agent"])
            else:
                anonymous_state = _get_anonymous_chat_state(request, agent.id)
                conversation_id = anonymous_state.get("conversation_id")
                if not conversation_id:
                    conversation = client.conversations.create()
                    conversation_id = conversation.id
                    _save_anonymous_chat_state(
                        request,
                        agent.id,
                        conversation_id=conversation_id,
                    )

            response_kwargs = {
                "input": [{"role": "user", "content": user_message}],
                "store": True,
                "model": agent.model or "gpt-5-mini",
            }
            if conversation_id:
                response_kwargs["conversation"] = conversation_id
            if agent.instructions:
                response_kwargs["instructions"] = agent.instructions

            response = client.responses.create(**response_kwargs)
            chatgpt_response = extract_response_text(response)
            chatgpt_response = render_markdown_with_latex(chatgpt_response)

            if canvas_user_id and len(canvas_user_id) > 0:
                prompt = Prompt.objects.create(
                    canvas_user=canvas_user,
                    course=course,
                    agent=agent,
                    prompt_text=user_message,
                    prompt_answer=chatgpt_response,
                )
                conversations = Prompt.objects.filter(
                    canvas_user=canvas_user,
                    course=course,
                    agent=agent,
                ).order_by("created")
            else:
                _save_anonymous_chat_state(
                    request,
                    agent.id,
                    message={"prompt_text": user_message, "prompt_answer": chatgpt_response},
                )
                conversations = _get_anonymous_chat_state(request, agent.id).get("messages", [])
            chat = []
            for c in conversations:
                if isinstance(c, dict):
                    chat.append({"prompt_text": c.get("prompt_text", ""), "prompt_answer": c.get("prompt_answer", "")})
                else:
                    chat.append({"prompt_text": c.prompt_text, "prompt_answer": c.prompt_answer})
            
            return JsonResponse({"reply": chatgpt_response,
                                "messages": chat})
        
        except Agent.DoesNotExist:
            print(f"Agent no encontrado para course_id: {course_id}.")
            print("No se ha añadido un asistente para este curso")
    
    return JsonResponse({"error": "Invalid request method"}, status=400)


@csrf_exempt
def reset_anonymous_conversation(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    data = json.loads(request.body or "{}")
    agent_pk = data.get("agent")
    if not agent_pk:
        return JsonResponse({"error": "Missing agent id"}, status=400)

    _save_anonymous_chat_state(request, agent_pk, reset=True)
    return JsonResponse({"ok": True})


class LTIRequestValidator(RequestValidator):
    def __init__(self):
        super().__init__()
        self.client_secrets = {"consumer_key_test": "shared_secret_test"}
        self.used_nonces = {}

    def validate_client_key(self, client_key, request):
        return client_key in self.client_secrets

    def get_client_secret(self, client_key, request):
        return self.client_secrets.get(client_key)

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce, request):
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 300:
            logger.warning(f"Invalid timestamp: {timestamp}")
            return False
        
        if nonce in self.used_nonces.get(client_key, set()):
            logger.warning(f"Nonce reused: {nonce}")
            return False
        
        self.used_nonces.setdefault(client_key, set()).add(nonce)
        return True


@csrf_exempt
@xframe_options_exempt
def lti_launch(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method. Only POST is allowed.")

    required_params = [
        "lti_message_type",
        "lti_version",
        "oauth_consumer_key",
        "resource_link_id",
    ]
    for param in required_params:
        if param not in request.POST or not request.POST[param]:
            return HttpResponseBadRequest(f"Missing required parameter: {param}")

    if request.POST["lti_message_type"] != "basic-lti-launch-request":
        return HttpResponseBadRequest("Invalid lti_message_type.")
    if request.POST["lti_version"] != "LTI-1p0":
        return HttpResponseBadRequest("Invalid lti_version.")

    canvas_user_id = request.POST.get("custom_canvas_user_id")
    course_id = request.POST.get("custom_canvas_course_id")
    user_login = request.POST.get("custom_canvas_user_login_id")
    course_title = request.POST.get("context_label")
    course, created = Course.objects.get_or_create(
        canvas_id=course_id,
        defaults={"title": f"Course {course_title}"}
    )
    if course.current_agent is None:
        return HttpResponse("This course does not yet have a defined agent.", status=400)
    agent = course.current_agent
    if not agent.api_key:
        return HttpResponse("The agent for this course does not have an API key configured.", status=400)

    canvas_user, _ = CanvasUser.objects.get_or_create(
        canvas_id=canvas_user_id, defaults={"login": user_login}
    )
    course, _ = Course.objects.get_or_create(
        canvas_id=course_id, defaults={"title": f"Course {course_title}"}
    )

    conversations = Prompt.objects.filter(
        canvas_user=canvas_user,
        course=course,
        agent=agent,
    ).order_by("created")
    messages = [{"prompt_text": c.prompt_text, "prompt_answer": c.prompt_answer} for c in conversations]

    template = loader.get_template('chatgpt.html')
    context = {
        "canvas_user": canvas_user_id,
        "course": course_id,
        "login": user_login,
        "course_title": course_title,
        "messages": messages,
        "agent_name": agent.name,
        "agent_id": agent.id,
    }
    return HttpResponse(template.render(context))


def course_dashboard(request, course_id):
    course = get_object_or_404(Course, id = course_id)
    prompts = Prompt.objects.filter(course = course)
    context = {
        "course" : course,
        "prompts" : prompts,
    }
    template = loader.get_template('chatbox/static/course_dashboard.html')
    return HttpResponse(template.render(context))


def teacher_student_chat_detail(request, course_id, canvas_user_id):
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)

    is_teacher = request.user.groups.filter(name="Teachers").exists()
    if not (is_teacher or request.user.is_superuser):
        return HttpResponse("Unauthorized", status=403)

    course = get_object_or_404(Course, id=course_id)
    canvas_user = get_object_or_404(CanvasUser, id=canvas_user_id)
    selected_agent = None

    if is_teacher and not request.user.is_superuser and course.created_by_id != request.user.id:
        return HttpResponse("Unauthorized", status=403)

    agent_id = request.GET.get("agent")
    prompts = Prompt.objects.filter(course=course, canvas_user=canvas_user)
    if agent_id:
        try:
            selected_agent = Agent.objects.get(id=int(agent_id))
            prompts = prompts.filter(agent=selected_agent)
        except (TypeError, ValueError, Agent.DoesNotExist):
            selected_agent = None
    prompts = prompts.order_by("created")

    context = {
        "course": course,
        "canvas_user": canvas_user,
        "selected_agent": selected_agent,
        "prompts": prompts,
        "total_prompts": prompts.count(),
        "last_interaction_at": prompts.last().created if prompts.exists() else None,
    }
    return render(request, "teacher_student_chat_detail.html", context)
