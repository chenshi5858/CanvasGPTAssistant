# Canvas ChatGPT Assistant

Canvas ChatGPT Assistant is a Django web application that integrates an AI tutoring chat into Canvas courses. It lets instructors configure course-specific AI agents, embed the chat experience through an LTI launch flow, store student conversations, and review interaction analytics from the Django admin.

The project was built as an educational AI tool rather than a generic chatbot: each course can have its own assistant instructions, model, OpenAI API key, conversation history, and reporting dashboard.

## What The Project Does

The application supports a full Canvas-based tutoring workflow:

1. Instructors configure an AI agent
   Teachers or administrators create an `Agent` in Django Admin, define its name, model, pedagogical instructions, and API key.

2. Courses are linked to agents
   Each Canvas course is represented by a `Course` record and can be assigned a current agent. This allows different courses to use different tutor behavior.

3. Students launch the tool from Canvas
   The app exposes an LTI launch endpoint that receives Canvas user and course information, creates local records when needed, and opens the chat interface inside the course context.

4. Conversations are preserved
   For each student, course, and agent combination, the system stores a conversation id from the OpenAI Responses API and keeps the full prompt/answer history in the database.

5. Teachers review usage
   Staff users can inspect student conversations, filter prompts, export data, and view course-level interaction summaries.

6. Interactions can be analyzed
   The admin dashboard can classify prompts into interaction types and answer correctness labels using an OpenAI model, helping instructors understand how students are using the tutor.

## Key Features

- Canvas-oriented AI tutoring chat.
- Basic LTI launch endpoint for Canvas course navigation.
- Course-specific AI agent configuration.
- Per-agent model, instructions, name, and API key.
- OpenAI Responses API integration with stored conversation ids.
- Anonymous test chat route for trying an agent outside Canvas.
- Markdown rendering with fenced code block support.
- Prompt and response persistence by student, course, and agent.
- Django Admin dashboards for instructors and administrators.
- Teacher permission group with scoped access to owned courses.
- Prompt export to CSV and XLSX.
- Student interaction summary export to XLSX.
- Course summary dashboard with activity charts for the last 30 days.
- Background interaction analysis for prompt classification.
- Student conversation detail view for staff users.
- Course class schedules used to separate interactions during and outside class time.
- Heroku-compatible `Procfile` with Gunicorn.

## AI Workflow

When a student sends a message, the backend:

1. Resolves the active course agent from the Canvas course context.
2. Loads or creates the student's OpenAI conversation for that course and agent.
3. Sends the message to the OpenAI Responses API using the agent model and instructions.
4. Extracts the text output from the response.
5. Renders the answer as HTML-friendly Markdown.
6. Saves the prompt and answer as a `Prompt` record.
7. Returns the full conversation history to the chat UI.

The project also includes an admin-side analysis service that reviews saved prompts and classifies them using `gpt-4.1-mini` into:

- `answer`
- `clarification`
- `question`
- `out_of_context`

For interactions classified as answers, the service also labels correctness as:

- `correct`
- `partially_correct`
- `incorrect`
- `not_applicable`

## Main User Roles

- Student: launches the chat from Canvas and interacts with the AI tutor.
- Teacher: configures agents/courses they own, reviews prompts, and exports interaction data.
- Administrator: manages all agents, courses, users, permissions, and analytics.

## Tech Stack

### Backend

- Python
- Django 5.1
- Django Admin
- SQLite for local development
- PostgreSQL support through `DATABASE_URL`
- Gunicorn
- WhiteNoise
- OpenAI Python SDK
- PyLTI1p3 and OAuth libraries
- Markdown2
- django-daisy for admin styling

### Deployment And Operations

- Heroku-compatible `Procfile`
- Static files through WhiteNoise
- Environment-based database configuration with `dj-database-url`
- Teacher permission setup through a custom Django management command

## Repository Structure

```text
canvas-chatgpt-clean/
  manage.py
  requirements.txt
  Procfile
  chatbox_canvas/
    settings.py            Django settings
    urls.py                Project URL routing
    wsgi.py
    asgi.py
  chatbox/
    models.py              Agents, courses, Canvas users, prompts, summaries
    views.py               Chat UI, OpenAI response endpoint, LTI launch
    admin.py               Admin dashboards, exports, analytics
    utils.py               Response extraction and Markdown rendering
    services/
      prompt_analysis.py   AI-based prompt classification
    management/commands/
      create_teacher_group.py
      seed_interactions_demo.py
    templates/
    static/
  staticfiles/
    tool_config.xml        Canvas LTI XML example
    tool_config.json       Canvas tool configuration example
```

## Important Models

- `Agent`: AI assistant configuration, including model, instructions, display name, API key, and owner.
- `Course`: Canvas course mapping with a current agent.
- `CourseClassSchedule`: schedule windows used to classify interactions as during or outside class.
- `CanvasUser`: local representation of a Canvas user.
- `Prompt`: saved student message, AI response, interaction labels, and analysis status.
- `UserCourse`: links a student, course, agent, and OpenAI conversation id.
- `CourseSummary`: proxy model for course-level analytics.
- `UserCourseInteractionSummary`: proxy model for student interaction reporting.

## Main Routes

- `/<agent_id>/`: opens a standalone test chat for an agent.
- `/chatgpt_response/`: receives chat messages and returns AI responses.
- `/chatgpt_reset_anonymous/`: resets anonymous test conversations.
- `/lti_launch/`: Canvas launch endpoint.
- `/dashboard/<course_id>/`: course prompt dashboard.
- `/teacher/student-chat/<course_id>/<canvas_user_id>/`: staff-only student conversation detail.
- `/admin/`: Django Admin interface.

## Local Development

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a local `.env` file if needed:

```env
DEBUG=True
DATABASE_URL=
```

Run migrations:

```powershell
python manage.py migrate
```

Create an admin user:

```powershell
python manage.py createsuperuser
```

Create the teacher permission group:

```powershell
python manage.py create_teacher_group
```

Start the development server:

```powershell
python manage.py runserver
```

Then open:

```text
http://127.0.0.1:8000/admin/
```

## Basic Setup Flow

1. Log in to Django Admin.
2. Create or edit an `Agent`.
3. Add the model name, instructions, and OpenAI API key for that agent.
4. Create or update a `Course` and assign the agent as its current agent.
5. Open `/<agent_id>/` to test the agent outside Canvas.
6. Configure Canvas to launch the tool through `/lti_launch/`.

## Demo Data

The project includes a command that creates demo courses, students, conversations, and prompt records:

```powershell
python manage.py seed_interactions_demo --clear
```

To associate demo data with a specific teacher:

```powershell
python manage.py seed_interactions_demo --teacher teacher_username --clear
```

## Canvas Configuration

Example Canvas tool configuration files are included in:

- `staticfiles/tool_config.xml`
- `staticfiles/tool_config.json`

Before using them in another deployment, update:

- domain
- launch URL
- target link URI
- consumer key
- shared secret
- Canvas placement settings

The active launch endpoint is:

```text
/lti_launch/
```

## Security Notes

- Do not commit `.env` files, API keys, database dumps, or Python cache files.
- The repository `.gitignore` excludes `.env`, `__pycache__/`, `*.pyc`, SQLite local databases, and common virtual environments.
- OpenAI API keys are configured per agent in the database and should be treated as secrets.
- The current settings include development defaults. For production, move Django secrets, LTI secrets, host restrictions, and trusted origins into environment variables.
- Use HTTPS in production, especially when embedding the tool in Canvas.

## Project Highlights

This project demonstrates a practical AI education integration: an LMS-embedded chat experience, instructor-configurable AI agents, persistent student conversations, analytics dashboards, role-based access, exports for academic review, and AI-assisted classification of student interactions.
