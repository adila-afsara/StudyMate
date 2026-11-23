
import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import CourseMaterial
from .flashcard_utils import generate_flashcards


logger = logging.getLogger(__name__)


@login_required
@require_POST
def generate_flashcards_view(request):
    try:
        # Read either JSON or normal form submissions.
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST

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

    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse(
            {"error": "Invalid request data."},
            status=400
        )

    # Allow access only to the student's own lecture.
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

    # Load lecture chunks saved during upload.
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

    try:
        with chunks_file.open(encoding="utf-8") as file:
            chunks = json.load(file)

        if not isinstance(chunks, list) or not all(
            isinstance(chunk, str) for chunk in chunks
        ):
            raise ValueError("Invalid saved lecture chunks.")

        # Call our tested Gemini flashcard generator.
        result = generate_flashcards(
            chunks,
            number_of_cards=number_of_cards,
            card_style=card_style
        )

        return JsonResponse({
            "material_id": material.id,
            "material_title": material.title,
            **result
        })

    except Exception:
        logger.exception("Flashcard generation failed.")

        return JsonResponse(
            {
                "error": (
                    "Unable to generate flashcards right now. "
                    "Please try again."
                )
            },
            status=503
        )

