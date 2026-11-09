from django.shortcuts import render
import json
import logging
import shutil

from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Course, CourseMaterial
from .embedding_utils import generate_query_embedding
from .faiss_utils import load_faiss_index, search_faiss
from .gemini_utils import generate_answer
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from courses.pdf_utils import extract_text_from_pdf
from courses.chunk_utils import split_text_into_chunks
from courses.embedding_utils import generate_embeddings
from courses.faiss_utils import create_faiss_index, save_faiss_index

from .models import Course



logger = logging.getLogger(__name__)


@require_POST
def ask_studymate(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON request."},
            status=400
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Expected a JSON object."},
            status=400
        )

    question = data.get("question")
    material_id = data.get("material_id")
    response_mode = data.get("response_mode", "simple")

    if response_mode not in (
        "simple",
        "normal",
        "example_based",
        "exam_oriented"
    ):
        return JsonResponse(
            {"error": "Invalid response mode."},
            status=400
        )

    if not isinstance(question, str) or not question.strip():
        return JsonResponse(
            {"error": "Please enter a question."},
            status=400
        )

    question = question.strip()

    if len(question) > 2000:
        return JsonResponse(
            {"error": "Question is too long."},
            status=400
        )

    if isinstance(material_id, bool) or not str(material_id).isdigit():
        return JsonResponse(
            {"error": "A valid material ID is required."},
            status=400
        )

    # A temporary local-development endpoint.
    # Add authentication and course access checks
    # before allowing other users to access it.
    material = CourseMaterial.objects.filter(
        pk=int(material_id)
    ).first()

    if material is None:
        return JsonResponse(
            {"error": "Course material not found."},
            status=404
        )

    folder = (
        Path(settings.BASE_DIR)
        / "faiss_indexes"
        / f"material_{material.pk}"
    )

    if not (folder / "index.faiss").is_file() or not (
        folder / "chunks.json"
    ).is_file():
        return JsonResponse(
            {"error": "This PDF has not been indexed yet."},
            status=404
        )

    try:
        # Load saved vectors and text
        index, chunks = load_faiss_index(folder)

        # Convert the student's question into an embedding
        query_embedding = generate_query_embedding(question)

        # Retrieve the three most similar text chunks
        results = search_faiss(
            index, query_embedding, chunks, top_k=3
        )

        # Generate an answer using Gemini
        answer = generate_answer(
            question,
            results,
            response_mode=response_mode
        )

        return JsonResponse({
            "question": question,
            "answer": answer,
            "material_id": material.pk,
            "retrieved_chunks": len(results)
        })

    except Exception:
        logger.exception("StudyMate RAG request failed")

        return JsonResponse(
            {"error": "Unable to generate an answer right now."},
            status=500
        )

    

@ensure_csrf_cookie
def chatbot_page(request):
    return render(request, "StudyMate_chatbot.html")


def list_indexed_materials(request):
    materials = []

    for material in CourseMaterial.objects.select_related("course").all():
        folder = (
            Path(settings.BASE_DIR)
            / "faiss_indexes"
            / f"material_{material.pk}"
        )

        if (
            (folder / "index.faiss").is_file()
            and (folder / "chunks.json").is_file()
        ):
            materials.append({
                "id": material.pk,
                "title": material.title,
                "course": str(material.course)
            })

    return JsonResponse({"materials": materials})

@login_required
@ensure_csrf_cookie
def courses_page(request):
    return render(request, "StudyMate_courses.html")


@login_required
@require_POST
def add_course(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON data."},
            status=400
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Invalid request format."},
            status=400
        )

    code = data.get("course_code", "")
    name = data.get("course_name", "")

    if not isinstance(code, str) or not isinstance(name, str):
        return JsonResponse(
            {"error": "Invalid course information."},
            status=400
        )

    code = code.strip()
    name = name.strip()

    if not code or not name:
        return JsonResponse(
            {"error": "Course code and name are required."},
            status=400
        )

    if len(code) > 50 or len(name) > 200:
        return JsonResponse(
            {"error": "Course code or name is too long."},
            status=400
        )

    course = Course.objects.create(
        user=request.user,
        course_code=code,
        course_name=name
    )

    return JsonResponse({
        "message": "Course created successfully!",
        "course": {
            "id": course.pk,
            "course_code": course.course_code,
            "course_name": course.course_name
        }
    }, status=201)


from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

@login_required
def list_courses(request):
    courses = Course.objects.filter(
        user=request.user
    ).order_by("-created_at")

    course_data = []

    for course in courses:
        course_data.append({
            "id": course.id,
            "course_code": course.course_code,
            "course_name": course.course_name
        })

    return JsonResponse({
        "courses": course_data
    })



@login_required
@require_POST
def upload_material(request):
    # STEP 1: Receive PDF and course ID from the frontend
    course_id = request.POST.get("course_id")
    uploaded_file = request.FILES.get("file")

    if not course_id or not uploaded_file:
        return JsonResponse({
            "error": "Please select a course and PDF."
        }, status=400)

    # STEP 2: Verify that the course belongs to this user
    try:
        course = Course.objects.get(
            id=course_id,
            user=request.user
        )
    except (Course.DoesNotExist, ValueError, TypeError):
        return JsonResponse({
            "error": "Course not found."
        }, status=404)

    # STEP 3: Validate the uploaded file
    if not uploaded_file.name.lower().endswith(".pdf"):
        return JsonResponse({
            "error": "Only PDF files are supported."
        }, status=400)

    if uploaded_file.size > 20 * 1024 * 1024:
        return JsonResponse({
            "error": "PDF must be 20 MB or smaller."
        }, status=400)

    signature = uploaded_file.read(5)
    uploaded_file.seek(0)

    if signature != b"%PDF-":
        return JsonResponse({
            "error": "Invalid PDF file."
        }, status=400)

    material = None
    index_folder = None

    try:
        # STEP 4: Save the uploaded PDF and its database record
        material = CourseMaterial.objects.create(
            course=course,
            title=Path(uploaded_file.name).stem,
            file=uploaded_file
        )

        # STEP 5: Extract text from the saved PDF
        text = extract_text_from_pdf(
            material.file.path
        )

        if not text or not text.strip():
            raise ValueError(
                "No extractable text found in this PDF."
            )

        # STEP 6: Divide the extracted text into chunks
        chunks = split_text_into_chunks(text)

        if not chunks:
            raise ValueError(
                "No text chunks could be created."
            )

        # STEP 7: Convert chunks into numerical embeddings
        embeddings = generate_embeddings(chunks)

        # STEP 8: Create the FAISS vector index
        index = create_faiss_index(embeddings)

        # STEP 9: Choose the index storage folder
        index_folder = (
            settings.BASE_DIR
            / "faiss_indexes"
            / f"material_{material.id}"
        )

        # STEP 10: Save FAISS index and original chunks
        save_faiss_index(
            index,
            chunks,
            index_folder
        )

        # STEP 11: Return success to the frontend
        return JsonResponse({
            "message": "PDF uploaded and indexed successfully!",
            "material": {
                "id": material.id,
                "title": material.title,
                "course_id": course.id,
                "filename": material.file.name
            },
            "indexed": True,
            "total_chunks": len(chunks)
        }, status=201)

    except Exception as error:
        # Clean up this failed new upload so the database
        # does not contain a PDF marked as uploaded but
        # missing its completed FAISS index.
        if index_folder is not None:
            shutil.rmtree(index_folder, ignore_errors=True)

        if material is not None:
            material.file.delete(save=False)
            material.delete()

        # Keep technical details in the Django terminal.
        import logging
        logging.getLogger(__name__).exception(
            "PDF upload/indexing failed"
        )

        return JsonResponse({
            "error": (
                "PDF upload or indexing failed. "
                "Check the Django terminal for details."
            )
        }, status=500)


@login_required
def list_course_materials(request):
    """
    Retrieve all courses and their uploaded PDFs
    for the currently logged-in user.
    """

    courses = Course.objects.filter(
        user=request.user
    ).prefetch_related("materials")

    course_data = []

    for course in courses:

        material_data = []

        for material in course.materials.all():

            folder = (
                Path(settings.BASE_DIR)
                / "faiss_indexes"
                / f"material_{material.pk}"
            )

            indexed = (
                (folder / "index.faiss").is_file()
                and (folder / "chunks.json").is_file()
            )

            material_data.append({
                "id": material.id,
                "title": material.title,
                "filename": Path(material.file.name).name,
                "uploaded_at": material.uploaded_at.isoformat(),
                "indexed": indexed
            })

        course_data.append({
            "id": course.id,
            "course_code": course.course_code,
            "course_name": course.course_name,
            "materials": material_data
        })

    return JsonResponse({
        "courses": course_data
    })

