
import os
import json
import re

from google import genai
import time
import random
from google.genai.errors import ServerError


# ============================================================
# STEP 1: Generate quiz questions using Gemini
# ============================================================

def generate_quiz(
    chunks,
    number_of_questions=5,
    question_type="mcq",
    difficulty="Medium"
):

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    if not chunks:
        raise ValueError("No lecture content available.")

    if not isinstance(chunks, list) or not all(
        isinstance(chunk, str) for chunk in chunks
    ):
        raise ValueError("Invalid lecture content.")

    number_of_questions = int(number_of_questions)

    if number_of_questions not in (3, 5, 10):
        raise ValueError(
            "Number of questions must be 3, 5, or 10."
        )

    if question_type not in ("mcq", "tf", "sa", "mixed"):
        raise ValueError("Invalid question type.")

    if difficulty not in ("Easy", "Medium", "Hard"):
        raise ValueError("Invalid difficulty level.")

    # --------------------------------------------------------
    # Set up Gemini
    # --------------------------------------------------------

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or not api_key.strip():
        raise ValueError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key.strip())

    lecture_content = "\n\n".join(chunks)
    lecture_content = lecture_content[:25000]

    if not lecture_content.strip():
        raise ValueError("Lecture text is empty.")

    # --------------------------------------------------------
    # Question type instructions
    # --------------------------------------------------------

    type_instructions = {
        "mcq": (
            "Generate only multiple-choice questions. "
            "Each question must have exactly four options "
            "and one correct answer."
        ),

        "tf": (
            "Generate only True/False questions. "
            "Each question must have exactly two options: "
            "True and False."
        ),

        "sa": (
            "Generate only short-answer questions. "
            "Each question must have a concise model answer. "
            "Do not use multiple-choice options."
        ),

        "mixed": (
            "Generate a balanced combination of "
            "multiple-choice, True/False, and short-answer "
            "questions. Use all three types when possible."
        )
    }

    difficulty_instructions = {
        "Easy": (
            "Focus on basic definitions, terminology, "
            "and simple factual understanding."
        ),

        "Medium": (
            "Focus on understanding concepts, relationships, "
            "and applying ideas to straightforward examples."
        ),

        "Hard": (
            "Focus on deeper understanding, comparisons, "
            "analysis, and application of lecture concepts."
        )
    }

    # --------------------------------------------------------
    # Build Gemini prompt
    # --------------------------------------------------------

    prompt = f"""
You are an expert university teaching assistant.

Generate exactly {number_of_questions} high-quality
quiz questions using ONLY the supplied lecture content.

QUESTION TYPE:
{type_instructions[question_type]}

DIFFICULTY:
{difficulty_instructions[difficulty]}

IMPORTANT RULES:

1. All questions must be based on the lecture content.
2. Do not invent facts or unrelated information.
3. Avoid duplicate or nearly identical questions.
4. Cover different important lecture concepts.
5. Make questions understandable independently.
6. Use clear and accurate English.
7. Every question must have one correct answer.
8. Provide a brief explanation for every answer.
9. For MCQ, use exactly four plausible options.
10. For True/False, use exactly ["True", "False"].
11. For short answer, use an empty options list.
12. Correct_answer must be an integer index for
    MCQ and True/False questions.
13. Correct_answer must be a string for
    short-answer questions.
14. For mixed quizzes, distribute question types
    as evenly as possible.
15. If the lecture contains insufficient material,
    return fewer questions rather than inventing facts.
16. Return ONLY valid JSON, with no Markdown.

OUTPUT FORMAT:

{{
    "questions": [
        {{
            "type": "mcq",
            "question": "Example multiple-choice question?",
            "options": [
                "Option A",
                "Option B",
                "Option C",
                "Option D"
            ],
            "correct_answer": 1,
            "explanation": "Explanation of the correct answer."
        }},
        {{
            "type": "tf",
            "question": "Example True/False statement.",
            "options": [
                "True",
                "False"
            ],
            "correct_answer": 0,
            "explanation": "Explanation of why it is true."
        }},
        {{
            "type": "sa",
            "question": "Example short-answer question?",
            "options": [],
            "correct_answer": "Concise model answer.",
            "explanation": "Brief explanation of the concept."
        }}
    ]
}}

LECTURE CONTENT:

{lecture_content}
"""

    # --------------------------------------------------------
    # Call Gemini
    # --------------------------------------------------------

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    result_text = response.text.strip()

    # Remove optional Markdown code fences.
    result_text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        result_text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Parse Gemini response
    # --------------------------------------------------------

    try:
        result = json.loads(result_text)

    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid quiz JSON."
        ) from error

    if not isinstance(result, dict):
        raise ValueError("Invalid quiz response format.")

    questions = result.get("questions", [])

    if not isinstance(questions, list):
        raise ValueError("Invalid quiz question data.")

    # --------------------------------------------------------
    # Validate generated questions
    # --------------------------------------------------------

    validated_questions = []
    seen_questions = set()

    for item in questions:

        if not isinstance(item, dict):
            continue

        q_type = item.get("type")
        question = item.get("question")
        options = item.get("options")
        correct_answer = item.get("correct_answer")
        explanation = item.get("explanation")

        if q_type not in ("mcq", "tf", "sa"):
            continue

        # For a single-type quiz, reject other types.
        if (
            question_type != "mixed"
            and q_type != question_type
        ):
            continue

        if not isinstance(question, str):
            continue

        if not isinstance(explanation, str):
            continue

        question = question.strip()
        explanation = explanation.strip()

        if not question or not explanation:
            continue

        if len(question) > 1000:
            continue

        if len(explanation) > 2000:
            continue

        normalized_question = " ".join(
            question.lower().split()
        )

        if normalized_question in seen_questions:
            continue

        # ----------------------------------------------------
        # MCQ validation
        # ----------------------------------------------------

        if q_type == "mcq":

            if not isinstance(options, list):
                continue

            if len(options) != 4:
                continue

            if not all(
                isinstance(option, str) and option.strip()
                for option in options
            ):
                continue

            options = [
                option.strip()
                for option in options
            ]

            if len(set(option.lower() for option in options)) != 4:
                continue

            if type(correct_answer) is not int:
                continue

            if correct_answer not in (0, 1, 2, 3):
                continue

        # ----------------------------------------------------
        # True/False validation
        # ----------------------------------------------------

        elif q_type == "tf":

            if options != ["True", "False"]:
                continue

            if type(correct_answer) is not int:
                continue

            if correct_answer not in (0, 1):
                continue

        # ----------------------------------------------------
        # Short-answer validation
        # ----------------------------------------------------

        elif q_type == "sa":

            if not isinstance(correct_answer, str):
                continue

            correct_answer = correct_answer.strip()

            if not correct_answer:
                continue

            if len(correct_answer) > 2000:
                continue

            options = []

        seen_questions.add(normalized_question)

        validated_questions.append({
            "type": q_type,
            "question": question,
            "options": options,
            "correct_answer": correct_answer,
            "explanation": explanation
        })

        if len(validated_questions) >= number_of_questions:
            break

    if not validated_questions:
        raise ValueError(
            "No valid quiz questions were generated."
        )

    # --------------------------------------------------------
    # Return validated quiz
    # --------------------------------------------------------

    return {
        "questions": validated_questions,
        "total_questions": len(validated_questions),
        "question_type": question_type,
        "difficulty": difficulty
    }


# ============================================================
# STEP 2: Grade short-answer quiz responses using Gemini
# ============================================================

def grade_short_answers(items):

    if not items:
        return []

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or not api_key.strip():
        raise ValueError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key.strip())

    prompt = f"""
You are a fair university examination evaluator.

Evaluate each student's short answer against the
corresponding model answer.

IMPORTANT RULES:

1. Evaluate meaning, not just matching keywords.
2. Accept answers that express the correct concept
   using different wording.
3. Accept concise but factually correct answers.
4. Reject answers that are factually incorrect.
5. Do not require students to use the exact wording
   of the model answer.
6. Do not award full correctness to incomplete
   or misleading answers.
7. Provide brief, constructive feedback.
8. Evaluate each answer independently.
9. Return ONLY valid JSON.

INPUT:

{json.dumps(items, ensure_ascii=False)}

OUTPUT FORMAT:

{{
    "results": [
        {{
            "index": 0,
            "is_correct": true,
            "feedback": "The answer correctly explains the concept."
        }}
    ]
}}

Return exactly one result for every input item.
"""

    response = generate_with_retry(
            client=client,
            prompt=prompt,
            max_attempts=3
    )

    if not response.text:
        raise ValueError("Gemini returned an empty grading response.")

    result_text = response.text.strip()

    result_text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        result_text,
        flags=re.IGNORECASE
    )

    try:
        data = json.loads(result_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid grading JSON."
        ) from error

    results = data.get("results", [])

    if not isinstance(results, list):
        raise ValueError("Invalid grading results.")

    validated = {}

    for item in results:

        if not isinstance(item, dict):
            continue

        index = item.get("index")
        is_correct = item.get("is_correct")
        feedback = item.get("feedback")

        if type(index) is not int:
            continue

        if not 0 <= index < len(items):
            continue

        if type(is_correct) is not bool:
            continue

        if not isinstance(feedback, str):
            continue

        validated[index] = {
            "is_correct": is_correct,
            "feedback": feedback.strip()[:1000]
        }

    if len(validated) != len(items):
        raise ValueError(
            "Gemini did not grade every short answer."
        )

    return [
        validated[index]
        for index in range(len(items))
    ]
def generate_with_retry(client, prompt, max_attempts=3):
    """
    Generate AI content using Gemini.

    If Gemini is temporarily unavailable (503),
    retry automatically with a short delay.
    """

    for attempt in range(max_attempts):

        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt
            )

            return response

        except ServerError as error:

            # Raise the error if all attempts have failed.
            if attempt == max_attempts - 1:
                raise error

            # Wait a little longer after each failed attempt.
            delay = (2 ** attempt) + random.uniform(0, 1)

            print(
                f"Gemini temporarily unavailable. "
                f"Retrying in {delay:.1f} seconds..."
            )

            time.sleep(delay)
