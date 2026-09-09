import logging
import markdown2

def extract_response_text(response):
    if getattr(response, "output_text", None):
        return response.output_text

    output = getattr(response, "output", []) or []
    chunks = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    text = "\n".join(chunks).strip()
    if text:
        return text

    logging.warning("No text content found in OpenAI response.")
    return ""


def clean_latex_escapes(text):
    text = text.replace('\\(', '\\\\(')
    text = text.replace('\\)', '\\\\)')
    text = text.replace('\\[', '\\\\[')
    text = text.replace('\\]', '\\\\]')
    return text


def render_markdown_with_latex(raw_text):
    cleaned = clean_latex_escapes(raw_text)
    html = markdown2.markdown(cleaned, extras=["fenced-code-blocks"])
    return html
