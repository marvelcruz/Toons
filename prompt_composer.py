import json
import re

from db import get_project, load_json, get_reference_asset


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value)).strip()


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def names_match(name, text):
    needle = normalize_name(name)
    haystack = normalize_name(text)
    return bool(needle and needle in haystack)


def scene_search_text(scene):
    return normalize_text(json.dumps(scene, ensure_ascii=False))


def _reference(
    project_id,
    kind,
    item,
    lock_key,
    negative_key=None,
    saved_lookup=None,
):
    name = item.get("name", "")
    if saved_lookup is None:
        saved = get_reference_asset(project_id, kind, name)
    else:
        saved = saved_lookup.get((kind, name))

    return {
        "name": name,
        "type": kind,
        "lock": item.get(lock_key, ""),
        "negative_lock": item.get(negative_key, "") if negative_key else "",
        "saved_reference": saved,
    }


def collect_scene_references(
    project_id,
    scene,
    project=None,
    bible=None,
    saved_lookup=None,
):
    if project is None:
        project = get_project(project_id)
    if bible is None:
        bible = load_json(project, "character_bible_json", {}) if project else {}
    search = scene_search_text(scene)

    characters = []
    for item in bible.get("characters", []):
        if names_match(item.get("name"), search):
            characters.append(
                _reference(
                    project_id,
                    "characters",
                    item,
                    "identity_lock",
                    "negative_identity_lock",
                    saved_lookup=saved_lookup,
                )
            )

    for item in bible.get("supporting_characters", []):
        if names_match(item.get("name"), search):
            characters.append(
                _reference(
                    project_id,
                    "supporting_characters",
                    item,
                    "identity_lock",
                    "negative_identity_lock",
                    saved_lookup=saved_lookup,
                )
            )

    groups = []
    for item in bible.get("character_groups", []):
        if names_match(item.get("name"), search):
            groups.append(
                _reference(
                    project_id,
                    "character_groups",
                    item,
                    "group_identity_lock",
                    "negative_group_lock",
                    saved_lookup=saved_lookup,
                )
            )

    location = None
    for item in bible.get("locations", []):
        if names_match(item.get("name"), search):
            location = _reference(
                project_id,
                "locations",
                item,
                "environment_lock",
                saved_lookup=saved_lookup,
            )
            break

    # Prefer the explicit scene location when the scene planner provided one.
    if not location and scene.get("location"):
        for item in bible.get("locations", []):
            if names_match(
                item.get("name"),
                scene.get("location"),
            ):
                location = _reference(
                    project_id,
                    "locations",
                    item,
                    "environment_lock",
                    saved_lookup=saved_lookup,
                )
                break

    props = []
    for item in bible.get("props", []):
        if names_match(item.get("name"), search):
            props.append(
                _reference(
                    project_id,
                    "props",
                    item,
                    "master_prop_prompt",
                    saved_lookup=saved_lookup,
                )
            )

    return {
        "characters": characters,
        "groups": groups,
        "location": location,
        "props": props,
    }


def build_style_block(bible):
    visual = bible.get("visual_direction", {})
    parts = [
        visual.get("overall_style"),
        visual.get("historical_direction"),
        visual.get("lighting_philosophy"),
        visual.get("camera_philosophy"),
    ]
    return "\n".join(str(v) for v in parts if v)


def compose_scene_package(
    project_id,
    scene,
    project=None,
    bible=None,
    saved_lookup=None,
):
    if project is None:
        project = get_project(project_id)
    if bible is None:
        bible = load_json(project, "character_bible_json", {}) if project else {}
    refs = collect_scene_references(
        project_id,
        scene,
        project=project,
        bible=bible,
        saved_lookup=saved_lookup,
    )

    locks = []
    negatives = []

    for ref in refs["characters"] + refs["groups"]:
        if ref.get("lock"):
            locks.append(f"{ref['name']}: {ref['lock']}")
        if ref.get("negative_lock"):
            negatives.append(ref["negative_lock"])

    if refs.get("location") and refs["location"].get("lock"):
        locks.append(
            f"Environment: {refs['location']['lock']}"
        )

    for ref in refs["props"]:
        if ref.get("lock"):
            locks.append(
                f"Prop - {ref['name']}: {ref['lock']}"
            )

    style = build_style_block(bible)

    start_state = (
        scene.get("start_state")
        or scene.get("start")
        or ""
    )
    action = (
        scene.get("dominant_action")
        or scene.get("action")
        or ""
    )
    end_state = (
        scene.get("end_state")
        or scene.get("end")
        or ""
    )

    spatial = "\n".join(
        str(x)
        for x in as_list(
            scene.get("physical_constraints")
        )
        if x
    )

    negative = "\n".join(
        str(x)
        for x in (
            as_list(scene.get("negative_constraints"))
            + negatives
        )
        if x
    )

    scene_prompt = scene.get("frame_prompt", "")
    video_prompt = scene.get("video_prompt", "")
    lock_block = "\n".join(locks)

    frame = f"""
{style}

CONTINUITY LOCKS
{lock_block}

SCENE IMAGE
{scene_prompt}

START STATE
{start_state}

DOMINANT ACTION
{action}

END STATE
{end_state}

PHYSICAL / SPATIAL CONSTRAINTS
{spatial}

NEGATIVE CONSTRAINTS
{negative}

Keep all named characters, recurring groups, locations and props consistent with their approved references. Do not invent costume, identity, geography or prop changes that conflict with the continuity locks.
""".strip()

    video = f"""
{style}

CONTINUITY LOCKS
{lock_block}

VIDEO DIRECTION
{video_prompt}

START STATE
{start_state}

DOMINANT ACTION
{action}

END STATE
{end_state}

The motion must visibly begin in the stated start state, progress through the dominant action, and finish in the stated end state. Preserve left/right position, entrances, exits, object orientation, gravity and environment geometry unless the scene explicitly changes them.

PHYSICAL / SPATIAL CONSTRAINTS
{spatial}

NEGATIVE CONSTRAINTS
{negative}

Preserve identity, costume, group uniforms, creature design, location geometry and prop design from the approved references throughout the shot.
""".strip()

    return {
        "references": refs,
        "frame_prompt": frame,
        "video_prompt": video,
    }


def reference_summary(package):
    refs = package.get("references", {})
    names = []

    for key in ("characters", "groups", "props"):
        for item in refs.get(key, []):
            names.append(
                {
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "approved": bool(item.get("saved_reference")),
                }
            )

    location = refs.get("location")
    if location:
        names.append(
            {
                "name": location.get("name"),
                "type": location.get("type"),
                "approved": bool(location.get("saved_reference")),
            }
        )

    return names
