"""Fast deterministic storyboard compiler for ToonScripture.

Takes an approved script and its Visual Bible and compiles an editable,
Flow-ready first scene plan. No provider calls or invented biblical events.
Subsequent human editing can add artistic choices as needed.
"""
import re


CAMERA_BEATS = (
    ("Wide establishing shot", "slow lateral drift"),
    ("Medium character-focused shot", "gentle push-in"),
    ("Close-up", "subtle camera hold"),
    ("Over-the-shoulder composition", "restrained lateral move"),
    ("Detailed insert shot", "slow rack focus"),
    ("Wide environmental composition", "gentle reveal"),
    ("Tracking composition", "controlled forward movement"),
    ("Intimate reaction composition", "steady held frame"),
)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _dialogue_text(lines):
    if not isinstance(lines, list):
        return ""
    pieces = []
    for line in lines:
        if isinstance(line, str):
            pieces.append(line.strip())
        elif isinstance(line, dict):
            pieces.append(_text(
                line.get("text") or line.get("line") or line.get("dialogue")
            ))
    return " ".join(x for x in pieces if x)


def script_story_beats(script):
    if not isinstance(script, dict):
        raise ValueError("The saved script must be a structured object.")
    pieces = []
    if _text(script.get("hook")):
        pieces.append(("Opening hook", script["hook"].strip()))
    sections = script.get("sections") or []
    if not isinstance(sections, list):
        raise ValueError("The saved script has an invalid sections field.")
    for idx, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            continue
        narr = _text(section.get("narration"))
        dialogue = _dialogue_text(section.get("dialogue"))
        beat = " ".join(part for part in (narr, dialogue) if part)
        if beat:
            pieces.append((_text(section.get("name")) or f"Story part {idx}", beat))
    if _text(script.get("closing")):
        pieces.append(("Closing", script["closing"].strip()))
    if not pieces:
        raise ValueError("The script does not have narration to turn into scenes.")
    return pieces


def _allocate_scenes(weights, desired):
    """Every non-empty story beat gets at least one scene."""
    desired = max(len(weights), min(desired, sum(weights)))
    counts = [1] * len(weights)
    for _ in range(desired - len(weights)):
        candidates = [i for i, w in enumerate(weights) if counts[i] < w]
        if not candidates:
            break
        best = max(candidates, key=lambda i: (weights[i] / (counts[i] + 1), -i))
        counts[best] += 1
    return counts


def _split_narration(text, desired):
    """Preserve every narration word, favoring nearby sentence endings."""
    words = text.split()
    if not words:
        return []
    desired = min(desired, len(words))
    parts = []
    left = 0
    for index in range(desired):
        remain_parts = desired - index
        if remain_parts == 1:
            end = len(words)
        else:
            limit = len(words) - (remain_parts - 1)
            ideal = left + round((len(words) - left) / remain_parts)
            ideal = max(left + 1, min(ideal, limit))
            options = [
                x for x in range(max(left + 1, ideal - 3),
                                 min(limit, ideal + 3) + 1)
                if re.search(r"[.!?;:]$", words[x - 1])
            ]
            end = min(options, key=lambda x: abs(x - ideal)) if options else ideal
        parts.append(" ".join(words[left:end]))
        left = end
    return parts


def _matching_names(items, narration):
    if not isinstance(items, list):
        return []
    haystack = re.sub(r"[^a-z0-9]+", " ", narration.casefold())
    haystack = f" {haystack.strip()} "
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        normalized = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
        if normalized and f" {normalized} " in haystack:
            found.append(name)
    return found


def _valid_items(bible, category):
    data = bible.get(category, [])
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _pick_title(narration, label, index):
    excerpt = " ".join(narration.split()[:6]).rstrip(",.;:!?")
    return f"{label} · {excerpt}" if excerpt else f"{label} · shot {index}"


def make_scene_plan(script, bible, target_seconds, progress=None):
    """Build scene draft without waiting for Gemini or OpenRouter.

    Completion events describe actual local preparation, not a simulated timer.
    Scene durations are finalized separately by the existing Flow timing fitter.
    """
    if not isinstance(bible, dict) or not bible:
        raise ValueError("Build the Visual Bible before preparing scenes.")
    def emit(pct, message):
        if progress:
            progress(pct, message)

    emit(10, "Reading approved narration and Visual Bible")
    beats = script_story_beats(script)
    total_words = sum(len(text.split()) for _, text in beats)
    if not total_words:
        raise ValueError("The script has no usable narration.")

    target_seconds = max(4, int(target_seconds))
    desired = max(1, round(target_seconds / 8))
    weights = [len(text.split()) for _, text in beats]
    counts = _allocate_scenes(weights, desired)
    emit(35, f"Mapping {sum(counts)} short clips across {len(beats)} story beats")

    char_items = _valid_items(bible, "characters") + _valid_items(
        bible, "supporting_characters"
    )
    group_items = _valid_items(bible, "character_groups")
    loc_items = _valid_items(bible, "locations")
    prop_items = _valid_items(bible, "props")
    scene_list = []
    last_location = ""
    for (label, narration), number in zip(beats, counts):
        last_characters = []
        for chunk in _split_narration(narration, number):
            n = len(scene_list) + 1
            camera, motion = CAMERA_BEATS[(n - 1) % len(CAMERA_BEATS)]
            focus = chunk.strip()
            lookup = f"{label}. {focus}"
            characters = _matching_names(char_items, lookup)
            groups = _matching_names(group_items, lookup)
            locations = _matching_names(loc_items, lookup)
            props = _matching_names(prop_items, lookup)
            if locations:
                last_location = locations[0]
            location = last_location
            if not characters and last_characters:
                characters = last_characters
            else:
                last_characters = characters
            character_cue = (
                ", ".join(characters + groups)
                if characters or groups else
                "The historical figures, environments or symbolic imagery explicitly supported by the script"
            )
            location_cue = (
                f"Established Visual Bible location: {location}."
                if location else
                "Keep the setting neutral unless the narration explicitly identifies it."
            )
            prop_cue = (
                "Approved prop references: " + ", ".join(props) + "."
                if props else
                "Do not invent new props."
            )
            visual_focus = focus[:260]
            start = (
                f"{camera}. Begin on the approved narrative beat: {visual_focus} "
                f"{location_cue}"
            )
            action = (
                f"Illustrate the narrated beat faithfully: {visual_focus}. "
                f"Focus: {character_cue}. Camera: {motion}."
            )
            end = (
                "End on a readable composition that can cut naturally to the "
                "next narrated beat without an identity, prop or location jump."
            )
            scene = {
                "scene_number": n,
                "scene_title": _pick_title(focus, label, n),
                "section_name": label,
                "narration": focus,
                "duration_seconds": 8,
                "shot_type": camera,
                "location": location,
                "characters": characters,
                "groups": groups,
                "props": props,
                "start_state": start,
                "dominant_action": action,
                "end_state": end,
                "frame_prompt": (
                    f"Cinematic historically grounded animated frame. {camera}. "
                    f"Depict this approved narrated moment: {visual_focus}. "
                    f"On-screen focus: {character_cue}. {location_cue} {prop_cue} "
                    "Preserve all Visual Bible appearance, costume and geometry locks. "
                    "Do not add unsupported biblical events."
                ),
                "video_prompt": (
                    f"One continuous shot illustrating: {visual_focus}. "
                    f"Start: {start} Main action: {action} End: {end} "
                    "Keep motion restrained and scene geography consistent."
                ),
                "physical_constraints": [
                    "Preserve approved Visual Bible identities, costumes and location geometry.",
                    "Keep scale, object orientation and character screen positions continuous.",
                ],
                "negative_constraints": [
                    "Do not invent additional Bible events, miracles, dialogue or characters.",
                    "No unexplained location, costume or prop changes.",
                ],
                "production_status": "not_started",
                "generation_mode": "instant_storyboard",
            }
            scene_list.append(scene)
    emit(85, "Applying continuity references and shot descriptions")
    return scene_list
