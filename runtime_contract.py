"""Runtime quality contract shared by script, narration and scene production.

The project's requested duration is authoritative until the user changes it.
Word counts estimate speaking time; only measured audio can confirm it.
"""
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_WORDS_PER_MINUTE = 150
WORD_TOLERANCE = 0.08
AUDIO_TOLERANCE = 0.08


def script_narration_text(script: dict) -> str:
    """Return the text spoken by the narrator in the existing script schema."""
    if not isinstance(script, dict):
        return ""
    parts: list[str] = []

    def add(value):
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    add(script.get("hook"))
    sections = script.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            add(section.get("narration"))
            if isinstance(section.get("dialogue"), list):
                for item in section["dialogue"]:
                    if isinstance(item, str):
                        add(item)
                    elif isinstance(item, dict):
                        add(item.get("line") or item.get("dialogue") or item.get("text"))
    add(script.get("closing"))
    return "\n\n".join(parts)


def _positive_minutes(value):
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        raise ValueError("Episode target runtime must be a number of minutes.")
    if not 0 < minutes <= 180:
        raise ValueError("Episode target runtime must be between 0 and 180 minutes.")
    return minutes


def script_runtime_report(script: dict, target_minutes: float) -> dict:
    """Estimate duration and explicitly grade how well the script meets the goal."""
    minutes = _positive_minutes(target_minutes)
    words = len(script_narration_text(script).split())
    target_words = round(minutes * DEFAULT_WORDS_PER_MINUTE)
    min_words = round(target_words * (1 - WORD_TOLERANCE))
    max_words = round(target_words * (1 + WORD_TOLERANCE))
    return {
        "target_minutes": minutes,
        "word_count": words,
        "target_words": target_words,
        "min_words": min_words,
        "max_words": max_words,
        "estimated_seconds": round(words / DEFAULT_WORDS_PER_MINUTE * 60),
        "matches_target": min_words <= words <= max_words,
        "status": (
            "on_target" if min_words <= words <= max_words
            else "too_short" if words < min_words
            else "too_long"
        ),
    }


def audio_runtime_report(actual_seconds, target_minutes: float) -> dict:
    """Compare measured saved audio with the requested episode duration."""
    minutes = _positive_minutes(target_minutes)
    try:
        seconds = float(actual_seconds)
    except (ValueError, TypeError):
        raise ValueError("Measured narration duration is unavailable.")
    if seconds <= 0:
        raise ValueError("Measured narration duration must be positive.")
    target_seconds = round(minutes * 60)
    tolerance = max(8, round(target_seconds * AUDIO_TOLERANCE))
    difference = round(seconds - target_seconds)
    return {
        "actual_seconds": round(seconds),
        "target_seconds": target_seconds,
        "difference_seconds": difference,
        "tolerance_seconds": tolerance,
        "matches_target": abs(difference) <= tolerance,
        "status": (
            "on_target" if abs(difference) <= tolerance
            else "too_short" if difference < 0 else "too_long"
        ),
    }


def runtime_label(seconds: int) -> str:
    seconds = max(0, round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"
