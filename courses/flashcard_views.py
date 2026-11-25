
import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from google.genai import errors as genai_errors

from .models import (
    CourseMaterial,
    FlashcardDeck,
    Flashcard,
)
from .flashcard_utils import generate_flashcards

logger = logging.getLogger(__name__)

# ============================================================
# STEP 1: Flashcards page
# ============================================================

@login_required
def flashcards_page(request):
    return render(request, "StudyMate_flashcards.html")

# ============================================================
# STEP 2: Generate flashcards from uploaded lecture chunks
# ============================================================

@login_required
@require_POST
def generate_flashcards_view(request):

    # --------------------------------------------------------
    # Read and validate request data
    # --------------------------------------------------------

    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST

        if (
            request.content_type == "application/json"
            and not isinstance(data, dict)
        ):
            raise ValueError("Invalid request format.")

        material_id = int(data.get("material_id"))
        number_of_cards = int(data.get("number_of_cards", 8))
        card_style = data.get("card_style", "q")

        if number_of_cards not in (5, 8, 12):
            return JsonResponse(
                {"error": "Choose 5, 8, or 12 cards."},
                status=400
            )

        if card_style not in ("term", "q", "cloze"):
            return JsonResponse(
                {"error": "Invalid card style."},
                status=400
            )

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError
    ):
        return JsonResponse(
            {"error": "Invalid request data."},
            status=400
        )

    # --------------------------------------------------------
    # Verify lecture ownership
    # --------------------------------------------------------

    try:
        material = CourseMaterial.objects.get(
            id=material_id,
            course__user=request.user
        )

    except CourseMaterial.DoesNotExist:
        return JsonResponse(
            {"error": "Lecture not found."},
            status=404
        )

    # --------------------------------------------------------
    # Locate saved lecture chunks
    # --------------------------------------------------------

    folder = (
        Path(settings.BASE_DIR)
        / "faiss_indexes"
        / f"material_{material.id}"
    )

    chunks_file = folder / "chunks.json"

    if not chunks_file.is_file():
        return JsonResponse(
            {"error": "Lecture chunks are not available."},
            status=404
        )

    # --------------------------------------------------------
    # Load saved lecture chunks
    # --------------------------------------------------------

    try:
        with chunks_file.open(encoding="utf-8") as file:
            chunks = json.load(file)

        if (
            not isinstance(chunks, list)
            or not chunks
            or not all(
                isinstance(chunk, str)
                for chunk in chunks
            )
        ):
            return JsonResponse(
                {"error": "Invalid or empty lecture content."},
                status=400
            )

    except (OSError, json.JSONDecodeError):
        logger.exception(
            "Unable to read saved lecture chunks."
        )

        return JsonResponse(
            {"error": "Unable to read lecture content."},
            status=500
        )

    # --------------------------------------------------------
    # Generate flashcards using Gemini
    # --------------------------------------------------------

    try:
        result = generate_flashcards(
            chunks,
            number_of_cards=number_of_cards,
            card_style=card_style
        )

        generated_cards = result["flashcards"]

        if not generated_cards:
            raise ValueError(
                "Gemini generated no flashcards."
            )

        # ----------------------------------------------------
        # Save deck and cards together in MySQL
        # ----------------------------------------------------

        with transaction.atomic():

            deck = FlashcardDeck.objects.create(
                user=request.user,
                material=material,
                title=f"{material.title} - Flashcards",
                card_style=card_style,
                total_cards=len(generated_cards)
            )

            Flashcard.objects.bulk_create([
                Flashcard(
                    deck=deck,
                    front=card["front"],
                    back=card["back"],
                    position=index
                )
                for index, card in enumerate(
                    generated_cards,
                    start=1
                )
            ])

        # ----------------------------------------------------
        # Return generated cards and saved deck information
        # ----------------------------------------------------

        return JsonResponse({
            "deck_id": deck.id,
            "material_id": material.id,
            "material_title": material.title,
            **result
        })

    # --------------------------------------------------------
    # Handle Gemini server errors
    # --------------------------------------------------------

    except genai_errors.ServerError:
        logger.exception(
            "Gemini server error during flashcard generation."
        )

        return JsonResponse(
            {
                "error": (
                    "The AI service is temporarily busy. "
                    "Please try again later."
                )
            },
            status=503
        )

    # --------------------------------------------------------
    # Handle Gemini client errors
    # --------------------------------------------------------

    except genai_errors.ClientError as error:
        logger.exception(
            "Gemini client error during flashcard generation."
        )

        status_code = error.code

        if status_code == 429:
            message = (
                "AI request limit reached. "
                "Please try again later."
            )
        else:
            message = (
                "The AI service could not process your request. "
                "Please try again."
            )

        return JsonResponse(
            {"error": message},
            status=(
                status_code
                if status_code in (400, 401, 403, 404, 429)
                else 502
            )
        )

    # --------------------------------------------------------
    # Handle unexpected application errors
    # --------------------------------------------------------

    except Exception:
        logger.exception(
            "Unexpected flashcard generation error."
        )

        return JsonResponse(
            {
                "error": (
                    "An unexpected error occurred "
                    "while generating flashcards."
                )
            },
            status=500
        )

# ============================================================
# STEP 3: Retrieve saved flashcard decks from MySQL
# ============================================================

@login_required
@require_GET
def list_flashcard_decks(request):

    decks = (
        FlashcardDeck.objects
        .filter(user=request.user)
        .select_related(
            "material",
            "material__course"
        )
        .prefetch_related("cards")
    )

    deck_list = []

    for deck in decks:

        cards = deck.cards.all()

        mastered_cards = sum(
            1 for card in cards if card.is_known
        )

        total_cards = deck.total_cards

        progress_percent = (
            round((mastered_cards / total_cards) * 100)
            if total_cards > 0
            else 0
        )

        card_list = [
            {
                "id": card.id,
                "front": card.front,
                "back": card.back,
                "is_known": card.is_known,
                "review_count": card.review_count,
                "position": card.position,
            }
            for card in cards
        ]

        deck_list.append({
            "id": deck.id,
            "title": deck.title,
            "card_style": deck.card_style,
            "total_cards": total_cards,
            "mastered_cards": mastered_cards,
            "progress_percent": progress_percent,
            "created_at": deck.created_at.isoformat(),

            "material": {
                "id": deck.material.id,
                "title": deck.material.title,
            },

            "course": {
                "id": deck.material.course.id,
                "course_code": deck.material.course.course_code,
                "course_name": deck.material.course.course_name,
            },

            "cards": card_list,
        })

    return JsonResponse({
        "decks": deck_list,
        "total_decks": len(deck_list),
    })

# ============================================================
# STEP 4: Update flashcard study progress
# ============================================================

@login_required
@require_POST
def update_flashcard_progress(request, card_id):

    # --------------------------------------------------------
    # Read progress information
    # --------------------------------------------------------

    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST

        if (
            request.content_type == "application/json"
            and not isinstance(data, dict)
        ):
            raise ValueError("Invalid request format.")

        is_known = data.get("is_known")

        # Accept JSON booleans or form values.
        if is_known in ("true", "True", "1"):
            is_known = True
        elif is_known in ("false", "False", "0"):
            is_known = False

        if not isinstance(is_known, bool):
            raise ValueError("Invalid progress value.")

    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse(
            {"error": "Invalid progress information."},
            status=400
        )

    # --------------------------------------------------------
    # Find card belonging to the logged-in student
    # --------------------------------------------------------

    try:
        card = Flashcard.objects.select_related(
            "deck"
        ).get(
            id=card_id,
            deck__user=request.user
        )

    except Flashcard.DoesNotExist:
        return JsonResponse(
            {"error": "Flashcard not found."},
            status=404
        )

    # --------------------------------------------------------
    # Save progress in MySQL
    # --------------------------------------------------------

    Flashcard.objects.filter(
        id=card.id
    ).update(
        is_known=is_known,
        review_count=F("review_count") + 1
    )

    card.refresh_from_db()

    # --------------------------------------------------------
    # Calculate updated deck progress
    # --------------------------------------------------------

    deck = card.deck

    mastered_cards = Flashcard.objects.filter(
        deck=deck,
        is_known=True
    ).count()

    total_cards = deck.total_cards

    progress_percent = (
        round((mastered_cards / total_cards) * 100)
        if total_cards > 0
        else 0
    )

    return JsonResponse({
        "success": True,
        "card_id": card.id,
        "is_known": card.is_known,
        "review_count": card.review_count,
        "mastered_cards": mastered_cards,
        "total_cards": total_cards,
        "progress_percent": progress_percent,
    })

# ============================================================
# STEP 5: Delete a flashcard deck
# ============================================================

@login_required
@require_POST
def delete_flashcard_deck(request, deck_id):

    try:
        deck = FlashcardDeck.objects.get(
            id=deck_id,
            user=request.user
        )

    except FlashcardDeck.DoesNotExist:
        return JsonResponse(
            {"error": "Flashcard deck not found."},
            status=404
        )

    # Deleting the deck also deletes its cards.
    # This happens because of on_delete=models.CASCADE.

    deck.delete()

    return JsonResponse({
        "success": True,
        "message": "Flashcard deck deleted successfully.",
        "deck_id": deck_id,
    })
