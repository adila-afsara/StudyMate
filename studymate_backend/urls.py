from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from courses import views as course_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Main chatbot page
    path("chatbot/", course_views.chatbot_page, name="chatbot_page"),

    # Courses and RAG API
    path("courses/", include("courses.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )