from django.urls import path
from . import views
from . import youtube_views
from . import flashcard_views


urlpatterns = [

    # My Courses page
    path(
        "",
        views.courses_page,
        name="courses_page"
    ),

    # Add a new course to MySQL
    path(
        "add/",
        views.add_course,
        name="add_course"
    ),

    # Retrieve the user's saved courses
    path(
        "list/",
        views.list_courses,
        name="list_courses"
    ),

    # Upload PDF and automatically create FAISS index
    path(
        "upload/",
        views.upload_material,
        name="upload_material"
    ),

    # All courses and uploaded PDFs for My Courses page
    path(
        "course-materials/",
        views.list_course_materials,
        name="list_course_materials"
    ),

    # Only indexed PDFs for the chatbot dropdown
    path(
        "materials/",
        views.list_indexed_materials,
        name="list_indexed_materials"
    ),

    # Student question -> FAISS retrieval -> Gemini answer
    path(
        "ask/",
        views.ask_studymate,
        name="ask_studymate"
    ),

    # Landing page
    path(
       "landing/",
        views.landing_page,
        name="landing_page"
    ),
    # Registration directly from landing page
    path(
        "landing-signup/",
        views.landing_signup,
        name="landing_signup"
    ),

        # YouTube Recommendations page
    path(
        "youtube/",
        youtube_views.youtube_recommendations_page,
        name="youtube_recommendations_page"
    ),

    # Generate YouTube recommendations
    path(
        "youtube/recommend/",
        youtube_views.get_youtube_recommendations,
        name="get_youtube_recommendations"
    ),

        # Generate AI flashcards from uploaded lecture chunks
    path(
        "flashcards/generate/",
        flashcard_views.generate_flashcards_view,
        name="generate_flashcards"
    ),
]
