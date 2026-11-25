
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from google.genai.errors import ServerError, ClientError

from .models import CourseMaterial, Quiz, QuizQuestion, QuizAttempt
from .quiz_utils import generate_quiz
from django.utils import timezone
from django.db.models import Count
from datetime import timedelta

from .models import QuizResponse
from .quiz_utils import grade_short_answers


# ============================================================
# GENERATE QUIZ FROM UPLOADED LECTURE
# ============================================================

@login_required
@require_POST
def generate_quiz_view(request):

    # --------------------------------------------------------
    # Read request
    # --------------------------------------------------------

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON request."},
            status=400
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Invalid request format."},
            status=400
        )

    material_id = data.get("material_id")
    question_type = data.get("question_type", "mcq")
    difficulty = data.get("difficulty", "Medium")
    topic = data.get("topic", "All topics")

    try:
        number_of_questions = int(
            data.get("number_of_questions", 5)
        )
        time_limit_seconds = int(
            data.get("time_limit_seconds", 0)
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "Invalid question count or time limit."},
            status=400
        )

    # --------------------------------------------------------
    # Validate quiz settings
    # --------------------------------------------------------

    if number_of_questions not in (3, 5, 10):
        return JsonResponse(
            {"error": "Select 3, 5, or 10 questions."},
            status=400
        )

    if question_type not in ("mcq", "tf", "sa", "mixed"):
        return JsonResponse(
            {"error": "Invalid question type."},
            status=400
        )

    if difficulty not in ("Easy", "Medium", "Hard"):
        return JsonResponse(
            {"error": "Invalid difficulty."},
            status=400
        )

    if time_limit_seconds not in (0, 120, 300, 600):
        return JsonResponse(
            {"error": "Invalid time limit."},
            status=400
        )

    # Topic filtering will be added separately.
    # For now, use the entire selected lecture.
    if topic != "All topics":
        return JsonResponse(
            {
                "error": (
                    "Topic filtering is not available yet. "
                    "Select All topics."
                )
            },
            status=400
        )

    # --------------------------------------------------------
    # Verify material belongs to logged-in student
    # --------------------------------------------------------

    material = get_object_or_404(
        CourseMaterial.objects.select_related("course"),
        pk=material_id,
        course__user=request.user
    )

    # --------------------------------------------------------
    # Load saved lecture chunks
    # --------------------------------------------------------

    chunks_file = (
        Path(settings.BASE_DIR)
        / "faiss_indexes"
        / f"material_{material.id}"
        / "chunks.json"
    )

    if not chunks_file.is_file():
        return JsonResponse(
            {
                "error": (
                    "Lecture chunks were not found. "
                    "Please index the material first."
                )
            },
            status=400
        )

    try:
        with open(chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        if not isinstance(chunks, list):
            raise ValueError("Invalid chunks format.")

        if not chunks or not all(
            isinstance(chunk, str) for chunk in chunks
        ):
            raise ValueError("Invalid lecture chunks.")

    except (OSError, ValueError, json.JSONDecodeError):
        return JsonResponse(
            {"error": "Unable to read lecture chunks."},
            status=400
        )

    # --------------------------------------------------------
    # Generate questions using Gemini
    # --------------------------------------------------------

    try:
        result = generate_quiz(
            chunks=chunks,
            number_of_questions=number_of_questions,
            question_type=question_type,
            difficulty=difficulty
        )

    except ServerError:
        return JsonResponse(
            {
                "error": (
                    "The AI service is temporarily busy. "
                    "Please try again later."
                )
            },
            status=503
        )

    except ClientError:
        return JsonResponse(
            {
                "error": (
                    "The AI service could not process the request. "
                    "Please check the API configuration or quota."
                )
            },
            status=502
        )

    except ValueError as error:
        return JsonResponse(
            {"error": str(error)},
            status=400
        )

    # --------------------------------------------------------
    # Save quiz and questions to MySQL
    # --------------------------------------------------------

    generated_questions = result["questions"]

    with transaction.atomic():

        quiz = Quiz.objects.create(
            user=request.user,
            material=material,
            title=f"{material.title} - Quiz",
            question_type=question_type,
            difficulty=difficulty,
            topic=topic,
            total_questions=len(generated_questions),
            time_limit_seconds=time_limit_seconds
        )

        saved_questions = QuizQuestion.objects.bulk_create([
            QuizQuestion(
                quiz=quiz,
                question_type=item["type"],
                question_text=item["question"],
                options=item["options"],
                correct_answer=item["correct_answer"],
                explanation=item["explanation"],
                position=index
            )
            for index, item in enumerate(
                generated_questions,
                start=1
            )
        ])

    # --------------------------------------------------------
    # Return safe question data
    # Correct answers remain on the server.
    # --------------------------------------------------------

    return JsonResponse({
        "success": True,
        "quiz_id": quiz.id,
        "title": quiz.title,
        "material_id": material.id,
        "material_title": material.title,
        "question_type": quiz.question_type,
        "difficulty": quiz.difficulty,
        "topic": quiz.topic,
        "total_questions": quiz.total_questions,
        "time_limit_seconds": quiz.time_limit_seconds,
        "questions": [
            {
                "id": question.id,
                "type": question.question_type,
                "question": question.question_text,
                "options": question.options,
                "position": question.position
            }
            for question in saved_questions
        ]
    }, status=201)


# ============================================================
# START QUIZ ATTEMPT
# ============================================================

@login_required
@require_POST
def start_quiz_attempt(request, quiz_id):

    # Get only a quiz belonging to the logged-in student.
    quiz = get_object_or_404(
        Quiz.objects.select_related("material"),
        id=quiz_id,
        user=request.user,
        material__course__user=request.user
    )

    questions = list(
        quiz.questions.order_by("position")
    )

    if not questions:
        return JsonResponse(
            {"error": "This quiz has no questions."},
            status=400
        )

    # Create a new attempt in MySQL.
    attempt = QuizAttempt.objects.create(
        quiz=quiz,
        user=request.user,
        status="in_progress"
    )

    # Return questions without correct answers.
    return JsonResponse({
        "success": True,
        "attempt_id": attempt.id,
        "quiz_id": quiz.id,
        "title": quiz.title,
        "status": attempt.status,
        "total_questions": len(questions),
        "time_limit_seconds": quiz.time_limit_seconds,
        "started_at": attempt.started_at.isoformat(),
        "questions": [
            {
                "id": question.id,
                "type": question.question_type,
                "question": question.question_text,
                "options": question.options,
                "position": question.position
            }
            for question in questions
        ]
    }, status=201)


# ============================================================
# SUBMIT QUIZ AND CALCULATE SCORE
# ============================================================

@login_required
@require_POST
def submit_quiz_attempt(request, attempt_id):

    # --------------------------------------------------------
    # Read request
    # --------------------------------------------------------

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON request."},
            status=400
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Invalid request format."},
            status=400
        )

    answers = data.get("answers")

    if not isinstance(answers, dict):
        return JsonResponse(
            {"error": "Answers must be provided as an object."},
            status=400
        )

    # --------------------------------------------------------
    # Verify attempt ownership
    # --------------------------------------------------------

    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz"),
        id=attempt_id,
        user=request.user,
        quiz__user=request.user
    )

    if attempt.status == "completed":
        return JsonResponse(
            {"error": "This quiz has already been submitted."},
            status=400
        )

    # --------------------------------------------------------
    # Enforce server-side time limit
    # --------------------------------------------------------

    now = timezone.now()

    time_taken = max(
        0,
        int((now - attempt.started_at).total_seconds())
    )

    time_limit = attempt.quiz.time_limit_seconds

    if time_limit and time_taken > time_limit:
        return JsonResponse(
            {"error": "The quiz time limit has expired."},
            status=400
        )

    # --------------------------------------------------------
    # Load questions
    # --------------------------------------------------------

    questions = list(
        attempt.quiz.questions.order_by("position")
    )

    if not questions:
        return JsonResponse(
            {"error": "No quiz questions found."},
            status=400
        )

    question_map = {
        str(question.id): question
        for question in questions
    }

    # Reject unknown question IDs.
    if not set(answers.keys()).issubset(question_map):
        return JsonResponse(
            {"error": "Invalid question ID submitted."},
            status=400
        )

    # --------------------------------------------------------
    # Validate and prepare answers
    # --------------------------------------------------------

    prepared_answers = {}

    for question in questions:

        question_id = str(question.id)
        student_answer = answers.get(question_id)

        if student_answer is None:
            prepared_answers[question.id] = None
            continue

        if question.question_type in ("mcq", "tf"):

            if type(student_answer) is not int:
                return JsonResponse(
                    {"error": "Invalid selected option."},
                    status=400
                )

            if not 0 <= student_answer < len(question.options):
                return JsonResponse(
                    {"error": "Selected option is out of range."},
                    status=400
                )

        elif question.question_type == "sa":

            if not isinstance(student_answer, str):
                return JsonResponse(
                    {"error": "Short answers must be text."},
                    status=400
                )

            student_answer = student_answer.strip()

            if len(student_answer) > 5000:
                return JsonResponse(
                    {"error": "Short answer is too long."},
                    status=400
                )

            if not student_answer:
                student_answer = None

        prepared_answers[question.id] = student_answer

    # --------------------------------------------------------
    # Grade MCQ and True/False questions
    # --------------------------------------------------------

    graded_responses = {}
    short_answer_items = []
    short_answer_ids = []

    for question in questions:

        student_answer = prepared_answers[question.id]

        if student_answer is None:
            graded_responses[question.id] = {
                "is_correct": False,
                "feedback": "Not answered."
            }
            continue

        if question.question_type in ("mcq", "tf"):

            is_correct = (
                student_answer == question.correct_answer
            )

            graded_responses[question.id] = {
                "is_correct": is_correct,
                "feedback": (
                    "Correct answer."
                    if is_correct
                    else "Incorrect answer."
                )
            }

        elif question.question_type == "sa":

            short_answer_items.append({
                "question": question.question_text,
                "model_answer": question.correct_answer,
                "student_answer": student_answer
            })

            short_answer_ids.append(question.id)

    # --------------------------------------------------------
    # Grade short answers using Gemini
    # --------------------------------------------------------

    if short_answer_items:

        try:
            grading_results = grade_short_answers(
                short_answer_items
            )

        except ServerError:
            return JsonResponse(
                {
                    "error": (
                        "AI grading is temporarily unavailable. "
                        "Please try submitting again."
                    )
                },
                status=503
            )

        except ClientError:
            return JsonResponse(
                {
                    "error": (
                        "AI grading could not process your answers."
                    )
                },
                status=502
            )

        except ValueError as error:
            return JsonResponse(
                {"error": str(error)},
                status=502
            )

        for question_id, grading in zip(
            short_answer_ids,
            grading_results
        ):

            graded_responses[question_id] = {
                "is_correct": grading["is_correct"],
                "feedback": grading["feedback"]
            }

    # --------------------------------------------------------
    # Calculate final score
    # --------------------------------------------------------

    correct_count = sum(
        1
        for result in graded_responses.values()
        if result["is_correct"]
    )

    total_questions = len(questions)

    score = round(
        (correct_count / total_questions) * 100,
        2
    )

    # --------------------------------------------------------
    # Save responses and complete attempt
    # --------------------------------------------------------

    from .models import QuizResponse

    with transaction.atomic():

        # Lock the attempt to prevent concurrent submissions.
        locked_attempt = (
            QuizAttempt.objects
            .select_for_update()
            .get(
                id=attempt.id,
                user=request.user
            )
        )

        if locked_attempt.status == "completed":
            return JsonResponse(
                {"error": "This quiz has already been submitted."},
                status=400
            )

        responses = []

        for question in questions:

            student_answer = prepared_answers[question.id]
            grading = graded_responses[question.id]

            responses.append(
                QuizResponse(
                    attempt=locked_attempt,
                    question=question,
                    student_answer=student_answer,
                    is_correct=grading["is_correct"],
                    feedback=grading["feedback"]
                )
            )

        QuizResponse.objects.bulk_create(responses)

        locked_attempt.correct_answers = correct_count
        locked_attempt.score = score
        locked_attempt.time_taken_seconds = time_taken
        locked_attempt.status = "completed"
        locked_attempt.completed_at = timezone.now()

        locked_attempt.save(
            update_fields=[
                "correct_answers",
                "score",
                "time_taken_seconds",
                "status",
                "completed_at"
            ]
        )

    # --------------------------------------------------------
    # Return results
    # --------------------------------------------------------

    return JsonResponse({
        "success": True,
        "attempt_id": attempt.id,
        "status": "completed",
        "total_questions": total_questions,
        "correct_answers": correct_count,
        "incorrect_answers": total_questions - correct_count,
        "score": float(score),
        "time_taken_seconds": time_taken,
        "results": [
            {
                "question_id": question.id,
                "question": question.question_text,
                "student_answer": prepared_answers[question.id],
                "correct_answer": question.correct_answer,
                "is_correct": graded_responses[question.id]["is_correct"],
                "explanation": question.explanation,
                "feedback": graded_responses[question.id]["feedback"]
            }
            for question in questions
        ]
    })

