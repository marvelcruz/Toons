import json
import os
import re
import time

from db import get_project, load_json, save_json


def _api_keys():
    keys = []

    def add(name, value):
        value = str(value or "").strip()
        if value and all(item["value"] != value for item in keys):
            keys.append({"name": name, "value": value})

    try:
        import streamlit as st
        session_key = st.session_state.get("gemini_api_key", "")
        add("browser_session", session_key)
    except Exception:
        pass

    add("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

    for letter in "ABCDEFGHI":
        name = f"GEMINI_API_KEY_{letter}"
        add(name, os.getenv(name, ""))

    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            add("GEMINI_API_KEY", st.secrets["GEMINI_API_KEY"])
        for letter in "ABCDEFGHI":
            name = f"GEMINI_API_KEY_{letter}"
            if name in st.secrets:
                add(name, st.secrets[name])
    except Exception:
        pass

    try:
        import streamlit as st
        selected = str(
            st.session_state.get("gemini_primary_name", "") or ""
        ).strip()

        if selected:
            chosen = [item for item in keys if item["name"] == selected]
            others = [item for item in keys if item["name"] != selected]
            if chosen:
                keys = chosen + others
    except Exception:
        pass

    return keys


def _api_key():
    keys = _api_keys()
    return keys[0]["value"] if keys else ""


def _api_key_count():
    return len(_api_keys())


def _api_key_names():
    return [item["name"] for item in _api_keys()]


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^\`\`\`(?:json)?\\s*", "", text, flags=re.I)
    text = re.sub(r"\\s*\`\`\`$", "", text)
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def call_json(system_prompt, user_prompt, temperature=0.3):
    key_entries = _api_keys()
    if not key_entries:
        raise RuntimeError(
            "Gemini is not connected yet. Add a Gemini API key in the deployment secrets."
        )

    import requests

    preferred = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    preferred = str(preferred or "").strip().strip('"').strip("'")
    if preferred.startswith("GEMINI_MODEL="):
        preferred = preferred.split("=", 1)[1].strip()
    if preferred.startswith("models/"):
        preferred = preferred.split("/", 1)[1].strip()

    models = []
    for model in [
        preferred,
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    ]:
        model = str(model or "").strip()
        if model and model not in models:
            models.append(model)

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    last_error = None

    # Primary project is the first configured key.
    # Backup projects are used only for auth/revocation/network/service failures.
    # A 429 quota response intentionally stops here rather than rotating projects.
    for key_index, key_entry in enumerate(key_entries):
        key = key_entry["value"]
        fail_over_to_next_key = False

        for model in models:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )

            for attempt in range(3):
                try:
                    response = requests.post(
                        url,
                        headers={
                            "x-goog-api-key": key,
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=120,
                    )

                    if response.ok:
                        data = response.json()
                        candidates = data.get("candidates") or []
                        if not candidates:
                            raise RuntimeError(
                                "Google returned no generated text. Please try again."
                            )

                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = "".join(
                            str(part.get("text") or "")
                            for part in parts
                        ).strip()

                        if not text:
                            raise RuntimeError(
                                "Google returned an empty response. Please try again."
                            )

                        return _extract_json(text)

                    status = response.status_code
                    last_error = RuntimeError(
                        f"Gemini returned HTTP {status}: {response.text[:800]}"
                    )

                    if status == 429:
                        raise RuntimeError(
                            "The primary Gemini API project's quota is temporarily exhausted. "
                            "ToonScripture did not switch projects automatically. "
                            "Please retry later or increase quota on the primary project."
                        )

                    if status in (401, 403):
                        fail_over_to_next_key = True
                        break

                    if status == 503:
                        if attempt < 2:
                            time.sleep(2 * (attempt + 1))
                            continue
                        fail_over_to_next_key = True
                        break

                    if status in (400, 404):
                        break

                    if status >= 500:
                        if attempt < 2:
                            time.sleep(2 * (attempt + 1))
                            continue
                        fail_over_to_next_key = True
                        break

                    raise last_error

                except requests.Timeout as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    fail_over_to_next_key = True
                    break

                except requests.RequestException as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    fail_over_to_next_key = True
                    break

            if fail_over_to_next_key:
                break

        if fail_over_to_next_key and key_index < len(key_entries) - 1:
            continue

        if fail_over_to_next_key:
            break

    raise RuntimeError(
        "Gemini could not complete this request with the configured primary project "
        "or its safe failover projects. "
        f"Last error: {last_error}"
    )


TREATMENT_SYSTEM = """
You are ToonScripture's Bible-story researcher and adaptation editor.
Create a retention-friendly treatment without inventing claims that contradict Scripture.
Separate scriptural facts, historically plausible interpretation, and cinematic continuity decisions.
Return valid JSON only.
"""

SCRIPT_SYSTEM = """
You are ToonScripture's long-form YouTube Bible-story writer.
Write cinematic, emotionally clear, family-friendly narration with strong retention.
Avoid preachy filler. Use sceneable language. Return valid JSON only.
"""

CRITIQUE_SYSTEM = """
You are a strict YouTube retention editor.
Review the script for hook strength, pacing, clarity, emotional escalation, repetition and payoff.
Return valid JSON only with score_100, strengths, problems, recommended_cuts, recommended_additions.
"""

SCENE_SYSTEM = """
You are ToonScripture's scene planner and prompt engineer.
Break the approved script into many short generation-ready scenes.
Every scene MUST contain:
scene_number, scene_title, narration, duration_seconds,
start_state, dominant_action, end_state,
physical_constraints, negative_constraints,
characters, location, frame_prompt, video_prompt.
The motion logic must always be start state -> dominant action -> end state.
Return valid JSON only with a scenes array.
"""

PACKAGE_SYSTEM = """
You are ToonScripture's YouTube packaging editor.
Create high-retention but truthful packaging.
Return valid JSON only with title_options, strongest_recommended_title,
strongest_thumbnail_recommendation, youtube_description and pinned_comment.
"""

BIBLE_SYSTEM = """
You are the character design director, world designer, costume supervisor and visual continuity
supervisor for ToonScripture.

Use four visual identity types:
1. major recurring named characters
2. supporting recurring individuals
3. character groups / uniform systems and creature groups
4. locations and props

A group is NOT a cloned individual. Lock shared visual culture, uniforms, armor, insignia,
weapons and silhouette while allowing natural facial/body variation.

Describe visible physical features directly. Never use ethnicity-coded anatomical stereotypes.
Separate scriptural fact, historically plausible interpretation and cinematic continuity decisions.

Visual style: premium cinematic 3D animated storytelling, sophisticated family-friendly stylized
realism, believable anatomy, expressive faces, detailed fabrics, realistic material response,
historically inspired environments, cinematic lighting, readable silhouettes.
Return valid JSON only.
"""


def develop_treatment(project_id):
    p = get_project(project_id)
    prompt = f"""
STORY: {p['story_name']}
BIBLE REFERENCE: {p['bible_reference']}
TARGET RUNTIME: {p['target_minutes']} minutes

Return:
{{
  "core_story": "",
  "scriptural_anchor": [],
  "historical_context": [],
  "cinematic_interpretations": [],
  "emotional_arc": "",
  "opening_hook": "",
  "story_beats": [],
  "accuracy_risks": [],
  "ending_payoff": ""
}}
"""
    out = call_json(TREATMENT_SYSTEM, prompt, 0.25)
    save_json(project_id, "treatment_json", out, "treatment_ready")
    return out


def draft_script(project_id):
    p = get_project(project_id)
    treatment = load_json(p, "treatment_json", {})
    prompt = f"""
TARGET RUNTIME: {p['target_minutes']} minutes
APPROVED TREATMENT:
{json.dumps(treatment, indent=2)}

Return:
{{
  "hook": "",
  "sections": [
    {{"name":"", "purpose":"", "narration":"", "dialogue":[]}}
  ],
  "closing": ""
}}
"""
    out = call_json(SCRIPT_SYSTEM, prompt, 0.35)
    save_json(project_id, "script_json", out, "script_ready")
    return out


def critique_script(project_id):
    p = get_project(project_id)
    script = load_json(p, "script_json", {})
    out = call_json(CRITIQUE_SYSTEM, json.dumps(script, indent=2), 0.15)
    save_json(project_id, "critique_json", out)
    return out


def plan_scenes(project_id):
    p = get_project(project_id)
    script = load_json(p, "script_json", {})
    bible = load_json(p, "character_bible_json", {})
    prompt = f"""
STORY: {p['story_name']}
TARGET RUNTIME: {p['target_minutes']} minutes

SCRIPT:
{json.dumps(script, indent=2)}

CHARACTER/WORLD BIBLE:
{json.dumps(bible, indent=2)}

Create as many useful visual scenes as needed for cinematic pacing.
"""
    out = call_json(SCENE_SYSTEM, prompt, 0.2)
    for scene in out.get("scenes", []):
        scene.setdefault("production_status", "not_started")
    save_json(project_id, "scenes_json", out, "scenes_ready")
    return out


def make_package(project_id):
    p = get_project(project_id)
    script = load_json(p, "script_json", {})
    prompt = f"STORY: {p['story_name']}\nSCRIPT:\n{json.dumps(script, indent=2)}"
    out = call_json(PACKAGE_SYSTEM, prompt, 0.55)
    save_json(project_id, "package_json", out)
    return out


def _context(p):
    return f"""
STORY: {p['story_name']}
BIBLE REFERENCE: {p['bible_reference']}
TARGET RUNTIME: {p['target_minutes']} minutes
TREATMENT:
{json.dumps(load_json(p, 'treatment_json', {}), indent=2)}
SCRIPT:
{json.dumps(load_json(p, 'script_json', {}), indent=2)}
"""


def build_character_bible(project_id):
    p = get_project(project_id)
    context = _context(p)

    major = call_json(BIBLE_SYSTEM, context + """
PASS 1 OF 4: MAJOR CHARACTERS ONLY.
Return:
{
 "visual_direction":{
   "overall_style":"","historical_direction":"","lighting_philosophy":"",
   "color_philosophy":"","camera_philosophy":"","family_safety_rules":[]
 },
 "characters":[{
   "name":"","role":"","source_classification":{"scriptural_facts":[],"historical_interpretations":[],"cinematic_continuity_decisions":[]},
   "apparent_age":"","gender":"","cultural_context":"",
   "physical_design":{},"costume_design":{},"performance_design":{},
   "continuity_locks":[],"forbidden_changes":[],
   "identity_lock":"","negative_identity_lock":"","master_character_prompt":""
 }]
}
""", 0.2)

    major_names = [x.get("name") for x in major.get("characters", [])]
    support = call_json(BIBLE_SYSTEM, context + f"""
ESTABLISHED MAJOR CHARACTERS: {json.dumps(major_names)}
PASS 2 OF 4: SUPPORTING CHARACTERS + GROUP/UNIFORM SYSTEMS + CREATURE GROUPS.
Do not recreate major characters.
Return:
{{
 "supporting_characters":[{{
   "name":"","role":"","apparent_age":"","gender":"","cultural_context":"",
   "physical_summary":"","costume_summary":"","performance_summary":"",
   "continuity_locks":[],"forbidden_changes":[],
   "identity_lock":"","negative_identity_lock":"","master_character_prompt":""
 }}],
 "character_groups":[{{
   "name":"","group_type":"","story_function":"","historical_context":"",
   "group_design":{{"gender_composition":"","age_range":"","complexion_range":"","build_range":"",
     "hair_rules":"","facial_hair_rules":"","uniform":"","armor":"","headwear":"",
     "footwear":"","weapons":[],"insignia":"","shared_colors":[],"rank_variants":[],
     "formation_behavior":"","movement_behavior":""}},
   "locked_group_traits":[],"allowed_individual_variation":[],"forbidden_changes":[],
   "group_identity_lock":"","negative_group_lock":"","master_group_prompt":""
 }}]
}}
""", 0.2)

    locations = call_json(BIBLE_SYSTEM, context + f"""
ESTABLISHED CHARACTERS: {json.dumps(major_names)}
ESTABLISHED GROUPS: {json.dumps([x.get('name') for x in support.get('character_groups', [])])}
PASS 3 OF 4: LOCATIONS ONLY.
Return:
{{
 "locations":[{{
   "name":"","story_purpose":"","historical_context":"",
   "physical_design":{{"architecture":"","materials":[],"floor":"","walls":"","ceiling":"",
     "columns":"","doors":"","windows":"","geometry":"","scale":"","entrances":[],
     "exits":[],"vertical_relationships":[],"horizontal_relationships":[],"geography":""}},
   "visual_layers":{{"foreground":"","midground":"","background":""}},
   "lighting":{{"day":"","night":"","practical_sources":[]}},
   "atmosphere":"","color_direction":"","recurring_props":[],
   "continuity_locks":[],"forbidden_changes":[],
   "environment_lock":"","master_environment_prompt":""
 }}]
}}
""", 0.2)

    props = call_json(BIBLE_SYSTEM, context + f"""
ESTABLISHED LOCATIONS: {json.dumps([x.get('name') for x in locations.get('locations', [])])}
PASS 4 OF 4: PROPS + GLOBAL CONTINUITY RULES ONLY.
Return:
{{
 "props":[{{
   "name":"","story_function":"","shape":"","dimensions_or_scale":"",
   "material":"","texture":"","color":"","markings":"",
   "usual_owner_or_location":"","interaction_logic":"",
   "continuity_locks":[],"master_prop_prompt":""
 }}],
 "global_continuity_rules":[],
 "historical_interpretation_notes":[],
 "generation_warnings":[]
}}
""", 0.2)

    final = {
        "visual_direction": major.get("visual_direction", {}),
        "characters": major.get("characters", []),
        "supporting_characters": support.get("supporting_characters", []),
        "character_groups": support.get("character_groups", []),
        "locations": locations.get("locations", []),
        "props": props.get("props", []),
        "global_continuity_rules": props.get("global_continuity_rules", []),
        "historical_interpretation_notes": props.get("historical_interpretation_notes", []),
        "generation_warnings": props.get("generation_warnings", []),
    }
    save_json(project_id, "character_bible_json", final, "bible_ready")
    return final

def narration_text(project_id):
    project = get_project(project_id)
    script = load_json(project, "script_json", {}) if project else {}

    parts = []

    if script.get("hook"):
        parts.append(str(script["hook"]).strip())

    for section in script.get("sections", []):
        narration = section.get("narration")
        if narration:
            parts.append(str(narration).strip())

        dialogue = section.get("dialogue")
        if isinstance(dialogue, list):
            for line in dialogue:
                if isinstance(line, str) and line.strip():
                    parts.append(line.strip())
                elif isinstance(line, dict):
                    text = (
                        line.get("line")
                        or line.get("dialogue")
                        or line.get("text")
                    )
                    if text:
                        parts.append(str(text).strip())

    if script.get("closing"):
        parts.append(str(script["closing"]).strip())

    return "\n\n".join(part for part in parts if part)


def list_tts_voices():
    key = _api_key()
    if not key:
        return [
            {"id": "Algenib", "display_name": "Algenib"},
            {"id": "Algieba", "display_name": "Algieba"},
        ]

    try:
        from google import genai

        client = genai.Client(api_key=key)
        items = client.voices.list(page_size=200)

        result = []
        for voice in items:
            data = (
                voice.model_dump()
                if hasattr(voice, "model_dump")
                else dict(voice)
            )
            result.append(data)

        return result or [
            {"id": "Algenib", "display_name": "Algenib"},
            {"id": "Algieba", "display_name": "Algieba"},
        ]
    except Exception:
        return [
            {"id": "Algenib", "display_name": "Algenib"},
            {"id": "Algieba", "display_name": "Algieba"},
        ]


def generate_tts_bytes(
    text,
    voice_id="Algenib",
    style_instruction="",
):
    key = _api_key()
    if not key:
        raise RuntimeError(
            "AI is not connected yet. Add a Gemini API key from the app."
        )

    from google import genai

    client = genai.Client(api_key=key)
    model = os.getenv(
        "GEMINI_TTS_MODEL",
        "gemini-3.8-flash-tts",
    )

    parts = [
        {
            "text": text,
            "speech_metadata": {
                "style": (
                    style_instruction
                    or "Warm cinematic storyteller with clear diction."
                )
            },
        }
    ]

    response = client.models.generate_content(
        model=model,
        contents=[
            {
                "role": "user",
                "parts": parts,
            }
        ],
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "voice": voice_id,
                }
            },
        },
    )

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError(
            "The TTS request finished, but no audio candidate was returned."
        )

    content = getattr(candidates[0], "content", None)
    response_parts = getattr(content, "parts", None) or []

    for part in response_parts:
        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None)
        if data:
            if isinstance(data, str):
                import base64
                return base64.b64decode(data)
            return bytes(data)

    raise RuntimeError(
        "The TTS request finished, but no audio file was returned."
    )



def review_scene_frame(project_id, scene, image_bytes, mime_type):
    key = _api_key()
    if not key:
        raise RuntimeError(
            "AI is not connected yet. Add a Gemini API key from the app."
        )

    from google import genai
    from google.genai import types

    project = get_project(project_id)
    bible = load_json(project, "character_bible_json", {}) if project else {}

    prompt = f"""
You are ToonScripture's visual continuity supervisor.

Review the supplied generated frame against the intended scene and the Character/World Bible.

SCENE:
{json.dumps(scene, indent=2)}

CHARACTER / WORLD BIBLE:
{json.dumps(bible, indent=2)}

Judge only what can reasonably be seen in the image.

Return JSON:
{{
  "verdict": "approved" | "minor_fix" | "regenerate",
  "overall_score": 0,
  "identity_score": 0,
  "scene_accuracy_score": 0,
  "environment_score": 0,
  "physical_logic_score": 0,
  "technical_quality_score": 0,
  "what_matches": [],
  "problems": [],
  "regeneration_instruction": ""
}}

Use "approved" only when the frame is safe to continue.
Use "minor_fix" when the concept is correct but a small visible issue should be corrected.
Use "regenerate" when identity, scene action, spatial logic, environment, costume, prop, anatomy, or composition materially conflicts with the intended scene.
"""

    client = genai.Client(api_key=key)
    preferred = os.getenv("GEMINI_VISION_MODEL", "gemini-3.8-flash")

    response = client.models.generate_content(
        model=preferred,
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            ),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    return _extract_json(response.text)
