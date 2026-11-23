import json
import logging
import shutil
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from google.genai.errors import ServerError

from .models import Course, CourseMaterial
from .embedding_utils import generate_query_embedding, generate_embeddings
from .faiss_utils import (
    load_faiss_index,
    search_faiss,
    create_faiss_index,
    save_faiss_index,
)
from .gemini_utils import generate_answer
from .pdf_utils import extract_text_from_pdf
from .pptx_utils import extract_text_from_pptx
from .chunk_utils import split_text_into_chunks
from .query_utils import (
    normalize_query_for_retrieval,
    is_summary_request,
)


logger = logging.getLogger(__name__)


@login_required
@require_POST
def ask_studymate(request):
    # STEP 1: Read and validate the JSON request.
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON request."},
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Expected a JSON object."},
            status=400,
        )

    # STEP 2: Get and validate the student's question and response mode.
    question = data.get("question")
    material_id = data.get("material_id")
    response_mode = data.get("response_mode", "simple")

    valid_modes = (
        "simple",
        "normal",
        "example_based",
        "exam_oriented",
    )

    if response_mode not in valid_modes:
        return JsonResponse(
            {"error": "Invalid response mode."},
            status=400,
        )

    if not isinstance(question, str) or not question.strip():
        return JsonResponse(
            {"error": "Please enter a question."},
            status=400,
        )

    question = question.strip()

    if len(question) > 2000:
        return JsonResponse(
            {"error": "Question is too long."},
            status=400,
        )

    if isinstance(material_id, bool) or not str(material_id).isdigit():
        return JsonResponse(
            {"error": "A valid material ID is required."},
            status=400,
        )

    # STEP 3: Find the selected course material.
    # Only retrieve materials owned by the signed-in student.
    material = CourseMaterial.objects.filter(
        pk=int(material_id),
        course__user=request.user,
    ).first()

    if material is None:
        return JsonResponse(
            {"error": "Course material not found."},
            status=404,
        )

    # STEP 4: Locate the saved FAISS index for this material.
    folder = (
        Path(settings.BASE_DIR)
        / "faiss_indexes"
        / f"material_{material.pk}"
    )

    if not (folder / "index.faiss").is_file() or not (
        folder / "chunks.json"
    ).is_file():
        return JsonResponse(
            {"error": "This material has not been indexed yet."},
            status=404,
        )

    try:
        # STEP 5: Load the existing index and its matching text chunks.
        index, chunks = load_faiss_index(folder)

        if not chunks:
            return JsonResponse(
                {"error": "No lecture content found."},
                status=404,
            )

        # STEP 6: Detect whether the student is requesting a summary.
        summary_request = is_summary_request(question)

        if summary_request:
            # Summary requests use all saved chunks in their original order.
            # No embeddings or FAISS index need to be rebuilt.
            results = [
                {
                    "chunk": chunk,
                    "score": 0.0,
                    "chunk_number": chunk_number,
                }
                for chunk_number, chunk in enumerate(chunks, start=1)
            ]

            logger.info(
                "Summary request for material %s: using %s chunks.",
                material.pk,
                len(results),
            )

        else:
            # STEP 7: Normalize Bengali/Banglish questions for retrieval.
            # English questions are returned unchanged by this helper.
            search_query = normalize_query_for_retrieval(question)

            logger.info("Original question: %s", question)
            logger.info("Retrieval query: %s", search_query)

            # STEP 8: Generate an embedding for the retrieval query.
            query_embedding = generate_query_embedding(search_query)

            # STEP 9: Retrieve the three most relevant chunks.
            results = search_faiss(
                index,
                query_embedding,
                chunks,
                top_k=3,
            )

        if not results:
            return JsonResponse(
                {
                    "question": question,
                    "answer": "No relevant lecture content found.",
                    "material_id": material.pk,
                    "retrieved_chunks": 0,
                }
            )

        # STEP 10: Generate the answer using the ORIGINAL question.
        # Gemini can therefore respond in the student's language.
        answer = generate_answer(
            question,
            results,
            response_mode=response_mode,
        )

        # STEP 11: Return the answer and retrieval information.
        return JsonResponse(
            {
                "question": question,
                "answer": answer,
                "material_id": material.pk,
                "retrieved_chunks": len(results),
            }
        )

    except ServerError as error:
        # Handle temporary Gemini service errors separately.
        logger.warning(
            "Gemini service error during RAG request: %s",
            error,
        )

        status_code = getattr(error, "code", None)
        if status_code is None:
            status_code = getattr(error, "status_code", None)

        if str(status_code) == "503":
            return JsonResponse(
                {
                    "error": (
                        "Gemini is temporarily busy. "
                        "Please try your question again shortly."
                    )
                },
                status=503,
            )

        return JsonResponse(
            {
                "error": (
                    "Gemini is temporarily unavailable. "
                    "Please try again later."
                )
            },
            status=502,
        )

    except Exception:
        logger.exception("StudyMate RAG request failed")

        return JsonResponse(
            {"error": "Unable to generate an answer right now."},
            status=500,
        )


@login_required
@ensure_csrf_cookie
def chatbot_page(request):
    return render(request, "StudyMate_chatbot.html")


@login_required
def list_indexed_materials(request):
    materials = []

    for material in CourseMaterial.objects.select_related("course").filter(
        course__user=request.user
    ):
        folder = (
            Path(settings.BASE_DIR)
            / "faiss_indexes"
            / f"material_{material.pk}"
        )

        if (
            (folder / "index.faiss").is_file()
            and (folder / "chunks.json").is_file()
        ):
            materials.append(
                {
                    "id": material.pk,
                    "title": material.title,
                    "course": str(material.course),
                }
            )

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
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Invalid request format."},
            status=400,
        )

    code = data.get("course_code", "")
    name = data.get("course_name", "")

    if not isinstance(code, str) or not isinstance(name, str):
        return JsonResponse(
            {"error": "Invalid course information."},
            status=400,
        )

    code = code.strip()
    name = name.strip()

    if not code or not name:
        return JsonResponse(
            {"error": "Course code and name are required."},
            status=400,
        )

    if len(code) > 50 or len(name) > 200:
        return JsonResponse(
            {"error": "Course code or name is too long."},
            status=400,
        )

    course = Course.objects.create(
        user=request.user,
        course_code=code,
        course_name=name,
    )

    return JsonResponse(
        {
            "message": "Course created successfully!",
            "course": {
                "id": course.pk,
                "course_code": course.course_code,
                "course_name": course.course_name,
            },
        },
        status=201,
    )


@login_required
def list_courses(request):
    courses = Course.objects.filter(
        user=request.user
    ).order_by("-created_at")

    course_data = []

    for course in courses:
        course_data.append(
            {
                "id": course.id,
                "course_code": course.course_code,
                "course_name": course.course_name,
            }
        )

    return JsonResponse({"courses": course_data})


@login_required
@require_POST
def upload_material(request):
    # STEP 1: Receive a PDF/PPTX file and course ID.
    course_id = request.POST.get("course_id")
    uploaded_file = request.FILES.get("file")

    if not course_id or not uploaded_file:
        return JsonResponse(
            {"error": "Please select a course and a PDF or PPTX file."},
            status=400,
        )

    # STEP 2: Verify that the selected course belongs to this user.
    try:
        course = Course.objects.get(
            id=course_id,
            user=request.user,
        )
    except (Course.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {"error": "Course not found."},
            status=404,
        )

    # STEP 3: Validate file extension, size, and basic file structure.
    file_type = Path(uploaded_file.name).suffix.lower()

    if file_type not in (".pdf", ".pptx"):
        return JsonResponse(
            {
                "error": (
                    "Only PDF (.pdf) and PowerPoint (.pptx) "
                    "files are supported."
                )
            },
            status=400,
        )

    if uploaded_file.size > 20 * 1024 * 1024:
        return JsonResponse(
            {"error": "File must be 20 MB or smaller."},
            status=400,
        )

    if file_type == ".pdf":
        signature = uploaded_file.read(5)
        uploaded_file.seek(0)

        if signature != b"%PDF-":
            return JsonResponse(
                {"error": "Invalid PDF file."},
                status=400,
            )

    else:
        # A .pptx file is an Office Open XML ZIP package.
        try:
            uploaded_file.seek(0)

            with zipfile.ZipFile(uploaded_file) as package:
                required_parts = {
                    "[Content_Types].xml",
                    "ppt/presentation.xml",
                }

                if not required_parts.issubset(package.namelist()):
                    return JsonResponse(
                        {"error": "Invalid PowerPoint (.pptx) file."},
                        status=400,
                    )

        except (zipfile.BadZipFile, OSError, ValueError):
            return JsonResponse(
                {
                    "error": (
                        "Invalid or damaged PowerPoint (.pptx) file."
                    )
                },
                status=400,
            )

        finally:
            uploaded_file.seek(0)

    material = None
    index_folder = None

    try:
        # STEP 4: Save the uploaded file and create its database record.
        material = CourseMaterial.objects.create(
            course=course,
            title=Path(uploaded_file.name).stem,
            file=uploaded_file,
        )

        # STEP 5: Extract text using the appropriate file utility.
        if file_type == ".pdf":
            extracted_text = extract_text_from_pdf(material.file.path)
        else:
            extracted_text = extract_text_from_pptx(material.file.path)

        if not extracted_text or not extracted_text.strip():
            raise ValueError("No extractable text found in this file.")

        # STEP 6: Split extracted text into chunks.
        chunks = split_text_into_chunks(extracted_text)

        if not chunks:
            raise ValueError("No text chunks could be created.")

        # STEP 7: Generate multilingual embeddings for the chunks.
        embeddings = generate_embeddings(chunks)

        # STEP 8: Create the FAISS index.
        index = create_faiss_index(embeddings)

        # STEP 9: Select the per-material index folder.
        index_folder = (
            Path(settings.BASE_DIR)
            / "faiss_indexes"
            / f"material_{material.id}"
        )

        # STEP 10: Save the FAISS index and corresponding chunks.
        save_faiss_index(index, chunks, index_folder)

        # STEP 11: Return the upload result.
        return JsonResponse(
            {
                "message": (
                    f"{file_type[1:].upper()} uploaded and indexed "
                    "successfully!"
                ),
                "material": {
                    "id": material.id,
                    "title": material.title,
                    "course_id": course.id,
                    "filename": material.file.name,
                },
                "indexed": True,
                "total_chunks": len(chunks),
            },
            status=201,
        )

    except Exception:
        # Clean up only the material and index created by this failed upload.
        if index_folder is not None:
            shutil.rmtree(index_folder, ignore_errors=True)

        if material is not None:
            material.file.delete(save=False)
            material.delete()

        logger.exception("PDF/PPTX upload or indexing failed")

        return JsonResponse(
            {
                "error": (
                    "File upload or indexing failed. "
                    "Check the Django terminal for details."
                )
            },
            status=500,
        )


@login_required
def list_course_materials(request):
    """
    Retrieve courses and their uploaded PDF/PPTX materials
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

            material_data.append(
                {
                    "id": material.id,
                    "title": material.title,
                    "filename": Path(material.file.name).name,
                    "uploaded_at": material.uploaded_at.isoformat(),
                    "indexed": indexed,
                }
            )

        course_data.append(
            {
                "id": course.id,
                "course_code": course.course_code,
                "course_name": course.course_name,
                "materials": material_data,
            }
        )

    return JsonResponse({"courses": course_data})


@require_POST
def landing_signup(request):
    email = request.POST.get("email", "").strip().lower()
    password = request.POST.get("password", "")

    if not email or not password:
        return redirect("/accounts/signup/")

    User = get_user_model()

    if User.objects.filter(email__iexact=email).exists():
        return redirect("/accounts/login/")

    try:
        validate_password(password)
    except ValidationError:
        return redirect("/accounts/signup/")

    username_field = User.USERNAME_FIELD

    user_data = {
        username_field: email,
    }

    if username_field != "email":
        user_data["email"] = email

    user = User.objects.create_user(
        password=password,
        **user_data
    )

    login(
        request,
        user,
        backend="django.contrib.auth.backends.ModelBackend"
    )

    return redirect("/courses/")

def landing_page(request):
    return render(request, "studymate_landing_page.html")
