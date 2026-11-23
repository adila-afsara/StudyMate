
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404

from .models import CourseMaterial
from .faiss_utils import load_faiss_index
from .youtube_utils import recommend_youtube_videos


# ============================================================
# STEP 1: Display YouTube Recommendations page
# ============================================================

@login_required
def youtube_recommendations_page(request):

    # Retrieve only the logged-in student's materials.
    materials = CourseMaterial.objects.filter(
        course__user=request.user
    ).order_by("-uploaded_at")

    return render(
        request,
        "youtube_recommendations.html",
        {
            "materials": materials
        }
    )


# ============================================================
# STEP 2: Generate recommendations for selected lecture
# ============================================================

@login_required
def get_youtube_recommendations(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Only POST requests are allowed."},
            status=405
        )

    material_id = request.POST.get("material_id")

    if not material_id:
        return JsonResponse(
            {"error": "Please select a lecture."},
            status=400
        )

    # Verify that the material belongs to the logged-in student.
    material = get_object_or_404(
        CourseMaterial,
        id=material_id,
        course__user=request.user
    )

    # Locate the previously saved FAISS index and chunks.
    folder = (
        Path(settings.BASE_DIR)
        / "faiss_indexes"
        / f"material_{material.id}"
    )

    if not (
        (folder / "index.faiss").exists()
        and (folder / "chunks.json").exists()
    ):
        return JsonResponse(
            {
                "error": (
                    "This lecture has not been indexed yet. "
                    "Please upload or reprocess the material."
                )
            },
            status=400
        )

    try:

        # Load the existing FAISS index and lecture chunks.
        index, chunks = load_faiss_index(folder)

        if not chunks:
            return JsonResponse(
                {"error": "No lecture content was found."},
                status=400
            )

        # Generate three YouTube recommendations.
        recommendations = recommend_youtube_videos(chunks)

        return JsonResponse({
            "success": True,
            "material_title": material.title,
            "topics": recommendations["topics"],
            "videos": recommendations["videos"],
            "total_videos": recommendations["total_videos"]
        })

    except Exception:
        # Keep technical details in the server logs.
        import logging
        logging.exception(
            "YouTube recommendation generation failed."
        )

        return JsonResponse(
            {
                "error": (
                    "Unable to generate recommendations right now. "
                    "Please try again."
                )
            },
            status=500
        )

