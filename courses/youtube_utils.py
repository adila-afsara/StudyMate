
import os
import json
import re
import urllib.parse
import urllib.request
import urllib.error

from django.conf import settings
from google import genai


# ============================================================
# STEP 1: Extract important lecture topics using Gemini
# ============================================================


def extract_lecture_topics(chunks):

    if not chunks:
        raise ValueError("No lecture content available.")

    # Combine the original saved lecture chunks.
    lecture_content = "\n\n".join(chunks)

    # Limit the content sent to Gemini.
    lecture_content = lecture_content[:25000]

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or not api_key.strip():
        raise ValueError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key.strip())

    prompt = f"""
You are an expert university teaching assistant.

Your task is to carefully analyze the actual lecture
material and identify the THREE most important topics
for educational YouTube recommendations.

IMPORTANT: Analyze the supplied lecture content.
Do not rely on general knowledge to invent topics.

TOPIC IDENTIFICATION RULES:

1. Identify topics that are actually explained
   or demonstrated in the lecture.

2. Prioritize topics that receive substantial
   attention in the lecture.

3. Distinguish major topics from smaller subtopics.
   Combine closely related subtopics when appropriate.

4. Give priority to important technical concepts,
   frameworks, tools, methods and practical examples
   explicitly covered in the lecture.

5. Preserve the exact names of technical tools,
   programming languages, frameworks and methods.

6. If a framework such as JUnit or PyTest appears
   in the lecture, identify it explicitly when
   it represents an important teaching topic.

7. Do not recommend a topic merely because it is
   commonly associated with the lecture subject.

8. Do not assume that a topic is covered just because
   it appears in the course title.

9. Select THREE distinct topics rather than three
   differently worded versions of the same topic.

10. Consider the entire supplied lecture, including
    practical examples and demonstrations.

SEARCH QUERY RULES:

For each identified topic:

1. Create a specific English YouTube search query.
2. Include relevant technical terminology.
3. Make the query suitable for university students.
4. Prefer educational tutorials and detailed explanations.
5. Ensure the query closely matches what the lecture
   actually teaches.

OUTPUT FORMAT:

Return ONLY valid JSON.

Use exactly this structure:

{{
    "topics": [
        {{
            "topic": "Major lecture topic",
            "search_query": "Specific English YouTube search query"
        }},
        {{
            "topic": "Second major lecture topic",
            "search_query": "Specific English YouTube search query"
        }},
        {{
            "topic": "Third major lecture topic",
            "search_query": "Specific English YouTube search query"
        }}
    ]
}}

Do not include explanations outside the JSON.
Do not invent lecture topics.
Do not repeat the same topic in different words.

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
        data = json.loads(result_text)

    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid topic JSON."
        ) from error

    topics = data.get("topics", [])

    if not isinstance(topics, list) or len(topics) != 3:
        raise ValueError(
            "Gemini must identify exactly three topics."
        )

    validated_topics = []

    for item in topics:

        if not isinstance(item, dict):
            continue

        topic = item.get("topic")
        search_query = item.get("search_query")

        if (
            isinstance(topic, str)
            and isinstance(search_query, str)
            and topic.strip()
            and search_query.strip()
        ):
            validated_topics.append({
                "topic": topic.strip(),
                "search_query": search_query.strip()
            })

    if len(validated_topics) != 3:
        raise ValueError(
            "Three valid lecture topics are required."
        )

    return validated_topics



# ============================================================
# STEP 2: Search YouTube for educational videos
# ============================================================


def search_youtube_videos(topics):

    import html

    api_key = getattr(settings, "YOUTUBE_API_KEY", "")

    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing.")

    youtube_url = (
        "https://www.googleapis.com/youtube/v3/search"
    )

    videos = []
    seen_video_ids = set()

    for topic_data in topics:

        search_query = topic_data["search_query"]
        topic_name = topic_data["topic"]

        params = {
            "part": "snippet",
            "q": search_query + " educational lecture tutorial",
            "type": "video",
            "maxResults": 5,
            "relevanceLanguage": "en",
            "regionCode": "US",
            "safeSearch": "strict",
            "videoEmbeddable": "true",
            "videoSyndicated": "true",
            "key": api_key,
        }

        request_url = (
            youtube_url
            + "?"
            + urllib.parse.urlencode(params)
        )

        request = urllib.request.Request(
            request_url,
            headers={"Accept": "application/json"}
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=20
            ) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as error:

            error_body = error.read().decode(
                "utf-8",
                errors="replace"
            )

            raise ValueError(
                f"YouTube API returned HTTP {error.code}: "
                f"{error_body[:500]}"
            ) from error

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError
        ) as error:

            raise ValueError(
                "Unable to retrieve YouTube videos."
            ) from error

        # Select one unique video for this topic.
        for item in data.get("items", []):

            video_id = item.get(
                "id", {}
            ).get("videoId")

            snippet = item.get("snippet", {})

            if not video_id or video_id in seen_video_ids:
                continue

            title = html.unescape(
                snippet.get("title", "")
            )

            description = html.unescape(
                snippet.get("description", "")
            )

            channel = html.unescape(
                snippet.get("channelTitle", "")
            )

            if not title or not channel:
                continue

            thumbnails = snippet.get(
                "thumbnails", {}
            )

            thumbnail = (
                thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            ).get("url", "")

            videos.append({
                "video_id": video_id,
                "title": title,
                "channel": channel,
                "description": description,
                "thumbnail": thumbnail,
                "url": (
                    f"https://www.youtube.com/watch?v={video_id}"
                ),
                "topic": topic_name,
            })

            seen_video_ids.add(video_id)

            # Move to the next topic after finding one video.
            break

    if len(videos) != 3:
        raise ValueError(
            f"Expected 3 videos, but found {len(videos)}."
        )

    return videos



# ============================================================
# STEP 3: Complete recommendation pipeline
# ============================================================

def recommend_youtube_videos(chunks):

    # Identify important topics using Gemini.
    topics = extract_lecture_topics(chunks)

    # Find relevant educational videos.
    videos = search_youtube_videos(topics)

    return {
        "topics": topics,
        "videos": videos,
        "total_videos": len(videos)
    }

