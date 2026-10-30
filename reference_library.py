import hashlib
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


def active_reference_corpus():
    """Retrieve private, approved transcripts when available.

    Previously packaged excerpts remain a fallback, never a pretend complete
    corpus. Query only when a story needs reference preparation.
    """
    from db import load_private_style_corpus

    row = load_private_style_corpus()
    if row and isinstance(row.get("source_text"), str) and row["source_text"].strip():
        return row["source_text"], "private Supabase reference library"
    return load_reference_corpus(), "packaged reference excerpts"


def reference_source_status():
    text, origin = active_reference_corpus()
    size_bytes = len(text.encode("utf-8"))
    count_lines = len(text.splitlines())
    # Earlier source in the user's library was 854,528 bytes / 7,325 lines.
    complete = count_lines >= 7000 and size_bytes >= 800000
    return {
        "source": origin,
        "characters": len(text),
        "size_bytes": size_bytes,
        "lines": count_lines,
        "full_corpus_loaded": complete,
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def prepare_story_style(project):
    """Build a deterministic, episode-specific style brief from reference work."""
    if not project or not str(project.get("story_name") or "").strip():
        raise ValueError("Choose an episode with a story title first.")

    playbook = load_reference_playbook()
    if not playbook or not playbook.get("story_build_sequence"):
        raise RuntimeError(
            "The storytelling playbook is unavailable. Restore it before proceeding."
        )
    status = reference_source_status()
    if not status["size_bytes"]:
        raise RuntimeError(
            "No reference transcripts are available. Add the private corpus first."
        )

    excerpts = relevant_reference_excerpts(
        story_name=project.get("story_name"),
        bible_reference=project.get("bible_reference"),
        max_chunks=4,
        max_chars=16000,
    )
    if not excerpts:
        # Not every biblical character occurs in the reference collection.
        # Offer general technique examples rather than forcing false matches.
        corpus, _ = active_reference_corpus()
        excerpts = [
            {"relevance_score": 0, "excerpt": chunk}
            for chunk in _chunks(corpus, chunk_size=1400, overlap=0)[:2]
        ]
    focused = [
        {
            "relevance_score": x.get("relevance_score", 0),
            "excerpt": str(x.get("excerpt") or "")[:1800].strip(),
        }
        for x in excerpts if str(x.get("excerpt") or "").strip()
    ]
    if not focused:
        raise RuntimeError("The reference library has no usable storytelling excerpts.")

    return {
        "status": "ready",
        "story_name": project["story_name"],
        "bible_reference": project.get("bible_reference") or "",
        "target_minutes": project.get("target_minutes"),
        "reference_source": status,
        "playbook_name": playbook.get("name") or "ToonScripture Storytelling",
        "storytelling_method": playbook.get("story_build_sequence") or [],
        "quality_rules": playbook.get("non_negotiables") or [],
        "script_review_criteria": playbook.get("writer_room_scoring") or [],
        "adaptation_guardrail": playbook.get("adaptation_guardrail") or {},
        "relevant_reference_excerpts": focused,
        "selection_type": (
            "story_relevant" if any(x["relevance_score"] for x in focused)
            else "general_storytelling"
        ),
        "usage_rules": [
            "Learn techniques, not copyrighted wording; never reproduce reference prose.",
            "Use approved Scripture as factual authority, not the reference transcripts.",
            "Build a human emotional contradiction, specific future payoffs and clear narrative progression.",
            "Keep pacing and structure grounded in this episode's own story.",
            "Treat unknown historical details as interpretation, not scriptural facts.",
        ],
    }


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
    corpus, _ = active_reference_corpus()
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
    saved_brief = project.get("style_brief_json")
    if isinstance(saved_brief, str):
        try:
            saved_brief = json.loads(saved_brief)
        except ValueError:
            saved_brief = {}
    if isinstance(saved_brief, dict) and saved_brief.get("status") == "ready":
        return {
            "playbook": playbook,
            "prepared_story_style": saved_brief,
            "relevant_reference_excerpts": saved_brief.get("relevant_reference_excerpts", []),
            "usage_rules": saved_brief.get("usage_rules", []),
        }
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
