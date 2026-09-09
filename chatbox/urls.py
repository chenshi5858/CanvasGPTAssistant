from django.urls import path
from . import views

urlpatterns = [
    path('<int:agent_id>/', views.chatbox, name='chatgpt'),
    path('chatgpt_response/', views.chatgpt_response, name='chatgpt_response'),
    path('chatgpt_reset_anonymous/', views.reset_anonymous_conversation, name='chatgpt_reset_anonymous'),
    path(
        'teacher/student-chat/<int:course_id>/<int:canvas_user_id>/',
        views.teacher_student_chat_detail,
        name='teacher_student_chat_detail',
    ),
    path('lti_launch/', views.lti_launch, name='lti_launch'),
    path('dashboard/<int:course_id>/', views.course_dashboard, name='course_dashboard')
]
