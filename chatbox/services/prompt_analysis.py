import json
import logging

from django.utils import timezone
from openai import OpenAI

from chatbox.models import Prompt
from chatbox.utils import extract_response_text


logger = logging.getLogger(__name__)

INTERACTION_ANALYSIS_MODEL = "gpt-4.1-mini"
VALID_INTERACTION_TYPES = {
    Prompt.InteractionType.ANSWER,
    Prompt.InteractionType.CLARIFICATION,
    Prompt.InteractionType.QUESTION,
    Prompt.InteractionType.OUT_OF_CONTEXT,
}
VALID_ANSWER_CORRECTNESS = {
    Prompt.AnswerCorrectness.CORRECT,
    Prompt.AnswerCorrectness.PARTIALLY_CORRECT,
    Prompt.AnswerCorrectness.INCORRECT,
    Prompt.AnswerCorrectness.NOT_APPLICABLE,
}

ANALYSIS_INSTRUCTIONS = """
Analiza una interacción en un Intelligent Tutoring System (ITS).
Debes clasificar usando SOLO estos valores:
- interaction_type: answer | clarification | question | out_of_context
- answer_correctness: correct | partially_correct | incorrect | not_applicable

Reglas:
1) Usa prompt_text como base principal para interaction_type.
2) Usa previous_prompt_answer (respuesta del tutor en el turno anterior) para entender si prompt_text es una respuesta, aclaración o pregunta.
3) Usa current_prompt_answer como evidencia principal para determinar answer_correctness.
4) answer_correctness solo aplica cuando interaction_type = answer.
5) Si interaction_type != answer, answer_correctness debe ser not_applicable.
6) Responde SOLO JSON válido con este formato exacto:
{"interaction_type":"...","answer_correctness":"..."}
""".strip()


def _extract_first_json_object(raw_text):
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No se encontro un objeto JSON en la respuesta.")
    return raw_text[start : end + 1]


def analyze_prompt_interaction(prompt):
    if prompt.interaction_analyzed_at:
        return False, "already_analyzed"

    agent = prompt.agent or prompt.course.current_agent
    if not agent.api_key:
        prompt.interaction_analysis_error = "Agent API key not configured."
        prompt.save(update_fields=["interaction_analysis_error"])
        return False, "missing_api_key"

    client = OpenAI(api_key=agent.api_key)
    previous_prompt = (
        Prompt.objects.filter(
            course=prompt.course,
            canvas_user=prompt.canvas_user,
            agent=prompt.agent,
            created__lt=prompt.created,
        )
        .order_by("-created")
        .first()
    )
    if previous_prompt is None:
        # Fallback for very close timestamps.
        previous_prompt = (
            Prompt.objects.filter(
                course=prompt.course,
                canvas_user=prompt.canvas_user,
                agent=prompt.agent,
                id__lt=prompt.id,
            )
            .order_by("-id")
            .first()
        )

    payload = {
        "prompt_text": prompt.prompt_text,
        "previous_prompt_answer": previous_prompt.prompt_answer if previous_prompt else "",
        "current_prompt_answer": prompt.prompt_answer,
    }

    try:
        response = client.responses.create(
            model=INTERACTION_ANALYSIS_MODEL,
            input=[
                {"role": "system", "content": ANALYSIS_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": (
                        "Clasifica esta interacción y entrega SOLO JSON:\n"
                        f"{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
            store=False,
        )
        raw_text = extract_response_text(response)
        parsed = json.loads(_extract_first_json_object(raw_text))

        interaction_type = parsed.get("interaction_type")
        answer_correctness = parsed.get("answer_correctness")

        if interaction_type not in VALID_INTERACTION_TYPES:
            raise ValueError(f"interaction_type invalido: {interaction_type}")

        if interaction_type != Prompt.InteractionType.ANSWER:
            answer_correctness = Prompt.AnswerCorrectness.NOT_APPLICABLE

        if answer_correctness not in VALID_ANSWER_CORRECTNESS:
            raise ValueError(f"answer_correctness invalido: {answer_correctness}")

        prompt.interaction_type = interaction_type
        prompt.answer_correctness = answer_correctness
        prompt.interaction_analyzed_at = timezone.now()
        prompt.interaction_analysis_error = None
        prompt.save(
            update_fields=[
                "interaction_type",
                "answer_correctness",
                "interaction_analyzed_at",
                "interaction_analysis_error",
            ]
        )
        return True, None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error analyzing prompt id=%s", prompt.id)
        prompt.interaction_analysis_error = str(exc)
        prompt.save(update_fields=["interaction_analysis_error"])
        return False, str(exc)
