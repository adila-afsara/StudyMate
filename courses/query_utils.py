
import os
import re
import logging

from google import genai


logger = logging.getLogger(__name__)


# Common words used in Romanized Bengali
BANGLISH_MARKERS = {
    "ki", "kivabe", "kibhabe", "koy", "koto",
    "keno", "ken", "ache", "ase", "nai",
    "hoy", "hobe", "bolo", "bolte", "bujhao",
    "bujhay", "bujhiye", "eta", "ei", "er",
    "eita", "chapter", "erokom", "korbo",
    "kore", "kora", "theke", "jonno",
    "mane", "kirokom", "gulo", "gula"
}


# Terms indicating a chapter-summary request
SUMMARY_MARKERS = [
    "summary",
    "summarize",
    "summarise",
    "overview",
    "main points",
    "key points",
    "chapter summary",
    "summarize this chapter",
    "summarise this chapter",
    "এই অধ্যায়ের সারাংশ",
    "এই অধ্যায়ের সারাংশ",
    "অধ্যায়ের সারাংশ",
    "অধ্যায়ের সারাংশ",
    "সংক্ষেপে বল",
    "সারসংক্ষেপ",
    "মূল বিষয়গুলো",
    "মূল বিষয়গুলো",
    "ei chapter er summary",
    "ei chapter er saransho",
    "chapter er summary",
    "chapter er main points"
]


def contains_bengali(text):
    """Check whether text contains Bengali characters."""

    return any(
        "\u0980" <= char <= "\u09FF"
        for char in text
    )


def is_likely_banglish(question):
    """Identify likely Romanized Bengali questions."""

    words = set(
        re.findall(r"[a-zA-Z]+", question.lower())
    )

    return bool(words.intersection(BANGLISH_MARKERS))


def is_summary_request(question):
    """Identify requests for a chapter or topic summary."""

    question_lower = question.lower().strip()

    return any(
        marker in question_lower
        for marker in SUMMARY_MARKERS
    )


def normalize_query_for_retrieval(question):
    """
    Convert Bengali or Banglish questions into
    English retrieval queries.

    The original question remains unchanged
    for Gemini's final answer.
    """

    question = question.strip()

    # English questions do not need translation.
    if not contains_bengali(question) and not is_likely_banglish(question):
        return question

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.warning(
            "Gemini API key missing. Using original query."
        )
        return question

    try:
        client = genai.Client(api_key=api_key.strip())

        prompt = f"""
You are a multilingual search-query translator.

Translate the student's question into clear,
natural English for searching English academic
lecture notes.

RULES:
1. Preserve the exact meaning of the question.
2. Do not answer the question.
3. Do not summarize or explain anything.
4. Do not add information.
5. Preserve technical terms and course terminology.
6. Return only the English search query.

Student question:
{question}

English search query:
"""

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )

        normalized_query = (response.text or "").strip()

        # Remove accidental quotation marks.
        normalized_query = normalized_query.strip('"').strip("'")

        if not normalized_query:
            return question

        return normalized_query

    except Exception:
        logger.exception(
            "Query normalization failed. Using original question."
        )

        return question

