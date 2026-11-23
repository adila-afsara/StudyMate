
import os
import json
import re

from google import genai


# ============================================================
# STEP 1: Generate flashcards from saved lecture chunks
# ============================================================

def generate_flashcards(chunks, number_of_cards=8, card_style="q"):

    if not chunks:
        raise ValueError("No lecture content available.")

    number_of_cards = int(number_of_cards)

    if number_of_cards not in (5, 8, 12):
        raise ValueError("Number of cards must be 5, 8, or 12.")

    if card_style not in ("term", "q", "cloze"):
        raise ValueError("Invalid flashcard style.")

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or not api_key.strip():
        raise ValueError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key.strip())

    lecture_content = "\n\n".join(chunks)
    lecture_content = lecture_content[:25000]

    style_instructions = {
        "term": (
            "Each front must contain a technical term or concept. "
            "Each back must contain its accurate definition."
        ),
        "q": (
            "Each front must contain a clear study question. "
            "Each back must contain its correct answer."
        ),
        "cloze": (
            "Each front must contain a sentence with exactly "
            "one blank represented by ____. "
            "Each back must contain the missing word or short phrase."
        ),
    }

    prompt = f"""
You are an expert university teaching assistant.

Generate exactly {number_of_cards} useful revision flashcards
using ONLY the supplied lecture content.

FLASHCARD STYLE:
{style_instructions[card_style]}

IMPORTANT RULES:

1. Use concepts actually explained in the lecture.
2. Do not invent facts or introduce unrelated material.
3. Cover different important topics from the lecture.
4. Avoid duplicate or nearly identical flashcards.
5. Make each card understandable independently.
6. Keep answers accurate, concise and easy to memorize.
7. Prefer important definitions, concepts and examples.
8. Each front and back should normally be under 120 characters.
9. If the lecture does not contain enough distinct facts,
   do not invent extra flashcards.
10. Return ONLY valid JSON.

OUTPUT FORMAT:

{{
    "flashcards": [
        {{
            "front": "Question, term or fill-in-the-blank",
            "back": "Correct answer"
        }}
    ]
}}

LECTURE CONTENT:

{lecture_content}
"""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    result_text = response.text.strip()

    result_text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        result_text,
        flags=re.IGNORECASE
    )

    try:
        result = json.loads(result_text)

    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid flashcard JSON."
        ) from error

    flashcards = result.get("flashcards", [])

    if not isinstance(flashcards, list):
        raise ValueError("Invalid flashcard data.")

    validated_cards = []
    seen_fronts = set()

    for card in flashcards:

        if not isinstance(card, dict):
            continue

        front = card.get("front")
        back = card.get("back")

        if not isinstance(front, str) or not isinstance(back, str):
            continue

        front = front.strip()
        back = back.strip()

        if not front or not back:
            continue

        if len(front) > 120 or len(back) > 120:
            continue

        if front.lower() in seen_fronts:
            continue

        seen_fronts.add(front.lower())

        validated_cards.append({
            "front": front,
            "back": back
        })

    if not validated_cards:
        raise ValueError("No valid flashcards were generated.")

    return {
        "flashcards": validated_cards[:number_of_cards],
        "total_cards": len(validated_cards[:number_of_cards]),
        "style": card_style
    }

