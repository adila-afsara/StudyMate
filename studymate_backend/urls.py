
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from courses import views as course_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Signup, login, logout and social authentication
    path("accounts/", include("allauth.urls")),

    # Existing StudyMate chatbot
    path(
        "chatbot/",
        course_views.chatbot_page,
        name="chatbot_page"
    ),

    # Existing courses and RAG API
    path("courses/", include("courses.urls")),
        # StudyMate landing page
    path(
        "",
        course_views.landing_page,
        name="landing_page"
    ),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
