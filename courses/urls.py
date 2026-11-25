
from django.urls import path

from . import views
from . import youtube_views
from . import flashcard_views
from . import quiz_views



urlpatterns = [

    # ========================================================
    # MY COURSES
    # ========================================================

    path(
        "",
        views.courses_page,
        name="courses_page"
    ),

    path(
        "add/",
        views.add_course,
        name="add_course"
    ),

    path(
        "list/",
        views.list_courses,
        name="list_courses"
    ),

    path(
        "upload/",
        views.upload_material,
        name="upload_material"
    ),

    path(
        "course-materials/",
        views.list_course_materials,
        name="list_course_materials"
    ),

    path(
        "materials/",
        views.list_indexed_materials,
        name="list_indexed_materials"
    ),

    # ========================================================
    # CHATBOT
    # ========================================================

    path(
        "ask/",
        views.ask_studymate,
        name="ask_studymate"
    ),

    # ========================================================
    # LANDING PAGE
    # ========================================================

    path(
        "landing/",
        views.landing_page,
        name="landing_page"
    ),

    path(
        "landing-signup/",
        views.landing_signup,
        name="landing_signup"
    ),

    # ========================================================
    # YOUTUBE RECOMMENDATIONS
    # ========================================================

    path(
        "youtube/",
        youtube_views.youtube_recommendations_page,
        name="youtube_recommendations_page"
    ),

    path(
        "youtube/recommend/",
        youtube_views.get_youtube_recommendations,
        name="get_youtube_recommendations"
    ),

    # ========================================================
    # FLASHCARDS
    # ========================================================

    # Flashcards page
    path(
        "flashcards/",
        flashcard_views.flashcards_page,
        name="flashcards_page"
    ),

    # Generate AI flashcards
    path(
        "flashcards/generate/",
        flashcard_views.generate_flashcards_view,
        name="generate_flashcards"
    ),

    # Retrieve saved decks from MySQL
    path(
        "flashcards/decks/",
        flashcard_views.list_flashcard_decks,
        name="list_flashcard_decks"
    ),

    # Delete a saved deck
    path(
        "flashcards/decks/<int:deck_id>/delete/",
        flashcard_views.delete_flashcard_deck,
        name="delete_flashcard_deck"
    ),

    # Update flashcard study progress
    path(
        "flashcards/cards/<int:card_id>/progress/",
        flashcard_views.update_flashcard_progress,
        name="update_flashcard_progress"
    ),

    # ========================================================
    # FLASHCARDS
    # ========================================================

    path(
        "flashcards/",
        flashcard_views.flashcards_page,
        name="flashcards_page"
    ),

    path(
        "flashcards/generate/",
        flashcard_views.generate_flashcards_view,
        name="generate_flashcards"
    ),

    path(
        "flashcards/decks/",
        flashcard_views.list_flashcard_decks,
        name="list_flashcard_decks"
    ),

    path(
        "flashcards/decks/<int:deck_id>/delete/",
        flashcard_views.delete_flashcard_deck,
        name="delete_flashcard_deck"
    ),

    path(
        "flashcards/cards/<int:card_id>/progress/",
        flashcard_views.update_flashcard_progress,
        name="update_flashcard_progress"
    ),

    path("quiz/generate/", quiz_views.generate_quiz_view, name="generate_quiz"),
    
    path("quiz/<int:quiz_id>/start/", quiz_views.start_quiz_attempt, name="start_quiz_attempt"),
    path(
    "quiz/attempt/<int:attempt_id>/submit/",
    quiz_views.submit_quiz_attempt,
    name="submit_quiz_attempt"
    ),
    path(
    "quiz/<int:quiz_id>/start/",
    quiz_views.start_quiz_attempt,
    name="start_quiz_attempt"
    ),
    path(
    "quiz/",
    views.quiz_page,
    name="quiz_page"
    ),
]
