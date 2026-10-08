import json
import re
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CORPUS_PATH = BASE_DIR / "reference_data" / "ark_films_transcript_corpus.txt"
PLAYBOOK_PATH = BASE_DIR / "reference_data" / "ark_films_writing_playbook.json"


@lru_cache(maxsize=1)
def load_reference_playbook():
    try:
        return json.loads(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def load_reference_corpus():
    try:
        return CORPUS_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _keywords(*values):
    stop = {
        "the", "and", "for", "from", "with", "into", "story", "bible",
        "book", "chapter", "part", "episode", "animated", "movie", "film",
        "this", "that", "your", "their", "his", "her", "they", "them",
        "was", "were", "are", "is", "of", "to", "in", "a", "an"
    }
    words = []
    for value in values:
        text = str(value or "").lower()
        for word in re.findall(r"[a-z0-9']+", text):
            if len(word) >= 3 and word not in stop and word not in words:
                words.append(word)
    return words[:40]


def _chunks(text, chunk_size=6500, overlap=900):
    if not text:
        return []
    out = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + chunk_size)
        out.append(text[start:end])
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return out


def _chunk_score(chunk, keywords):
    lowered = chunk.lower()
    score = 0
    for keyword in keywords:
        count = lowered.count(keyword)
        if count:
            score += min(count, 8) * (3 if len(keyword) >= 6 else 2)

    # Prefer chunks containing actual transcript/narration rather than only metadata.
    for signal in (
        "stay with us until the end",
        "let's begin",
        "this is the story",
        "what would you do",
        "what happens when",
        "and so ends",
        "what can we learn",
    ):
        if signal in lowered:
            score += 3
    return score


def relevant_reference_excerpts(
    story_name="",
    bible_reference="",
    treatment=None,
    max_chunks=3,
    max_chars=16000,
):
    corpus = load_reference_corpus()
    if not corpus:
        return []

    treatment = treatment or {}
    key_values = [
        story_name,
        bible_reference,
        treatment.get("core_story"),
        treatment.get("viewer_promise"),
        treatment.get("central_dramatic_question"),
    ]

    for row in treatment.get("scriptural_anchor", []) or []:
        key_values.append(row if isinstance(row, str) else json.dumps(row))

    keywords = _keywords(*key_values)
    if not keywords:
        return []

    ranked = []
    for index, chunk in enumerate(_chunks(corpus)):
        score = _chunk_score(chunk, keywords)
        if score > 0:
            ranked.append((score, index, chunk))

    ranked.sort(key=lambda row: (-row[0], row[1]))

    selected = []
    used_chars = 0
    for score, index, chunk in ranked[: max_chunks * 3]:
        clean = re.sub(r"\n{3,}", "\n\n", chunk).strip()
        if not clean:
            continue

        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        if len(clean) > remaining:
            clean = clean[:remaining]

        selected.append(
            {
                "relevance_score": score,
                "excerpt": clean,
            }
        )
        used_chars += len(clean)
        if len(selected) >= max_chunks:
            break

    return selected


def writer_reference_context(project, treatment=None):
    playbook = load_reference_playbook()
    excerpts = relevant_reference_excerpts(
        story_name=project.get("story_name"),
        bible_reference=project.get("bible_reference"),
        treatment=treatment or {},
    )

    return {
        "playbook": playbook,
        "relevant_reference_excerpts": excerpts,
        "usage_rules": [
            "Treat the playbook as required storytelling craft guidance.",
            "Treat transcript excerpts as examples of successful structure and pacing, not as biblical authority.",
            "Do not copy distinctive wording from the reference corpus.",
            "Do not import invented events or biography from the reference corpus.",
            "When reference style conflicts with Scripture or the approved treatment, Scripture and the approved treatment win.",
        ],
    }


def compact_playbook_text():
    playbook = load_reference_playbook()
    if not playbook:
        return ""

    return json.dumps(
        {
            "non_negotiables": playbook.get("non_negotiables", []),
            "story_build_sequence": playbook.get("story_build_sequence", []),
            "writer_room_scoring": playbook.get("writer_room_scoring", []),
            "master_editor_questions": playbook.get("master_editor_questions", []),
            "adaptation_guardrail": playbook.get("adaptation_guardrail", {}),
        },
        ensure_ascii=False,
        indent=2,
    )
