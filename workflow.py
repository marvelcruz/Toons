import json
import os
import re
import time

from db import (
    get_project,
    load_json,
    save_json,
    record_ai_usage,
    list_project_assets,
    channel_performance_learning,
)


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
            st.session_state.get("gemini_primary_name", "")
            or os.getenv("GEMINI_PRIMARY_NAME", "")
            or ""
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


SECTION_KEY_MAP = {
    "treatment": "GEMINI_API_KEY_A",
    "script": "GEMINI_API_KEY_B",
    "retention": "GEMINI_API_KEY_C",
    "visual_bible": "GEMINI_API_KEY_I",
    "scenes": "GEMINI_API_KEY_E",
    "youtube": "GEMINI_API_KEY_F",
    "tts": "GEMINI_API_KEY_G",
    "vision": "GEMINI_API_KEY_H",
    "spare": "GEMINI_API_KEY_D",
}


def _api_keys_for(section):
    configured = _api_keys()
    target = SECTION_KEY_MAP.get(section)

    selected = []
    if target:
        selected.extend(
            item for item in configured
            if item["name"] == target
        )

    # Project D is the reserved spare. It is used only when the assigned
    # project is invalid, unavailable, or has a service-side failure.
    # It is never used to bypass a 429 quota response.
    if section != "spare":
        selected.extend(
            item for item in configured
            if item["name"] == "GEMINI_API_KEY_D"
            and all(existing["name"] != item["name"] for existing in selected)
        )

    if not selected and configured:
        selected.append(configured[0])

    return selected


def _api_key_for(section):
    entries = _api_keys_for(section)
    if not entries:
        return "", ""
    return entries[0]["value"], entries[0]["name"]


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


def _openrouter_key():
    return str(os.getenv("OPENROUTER_API_KEY", "") or "").strip()


def _call_qwen_json(system_prompt, user_prompt, temperature=0.3, section="general"):
    key = _openrouter_key()
    if not key:
        raise RuntimeError("OpenRouter is not connected.")

    import requests

    model = "openrouter/free"
    last_error = None

    # Let OpenRouter choose among its full free-model pool. Its free router
    # filters for request capabilities such as structured outputs. We retry
    # once because a free upstream provider can be temporarily busy or
    # rate-limited and a second request may be routed elsewhere.
    for attempt in range(2):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        user_prompt
                        + "\n\nReturn valid JSON only. Do not wrap it in markdown."
                    ),
                },
            ],
            "temperature": temperature,
            "max_tokens": 16384,
            "response_format": {"type": "json_object"},
        }

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://toonscripture.onrender.com",
                    "X-Title": "ToonScripture OS",
                },
                json=payload,
                timeout=180,
            )

            if not response.ok:
                record_ai_usage(
                    project_name="OPENROUTER_FREE_AI",
                    section_name=section,
                    model_name=model,
                    outcome="error",
                    http_status=response.status_code,
                )
                last_error = RuntimeError(
                    f"OpenRouter free router returned HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
                if response.status_code in (429, 502, 503, 504) and attempt == 0:
                    time.sleep(2)
                    continue
                break

            data = response.json()
            routed_model = str(data.get("model") or model)
            choices = data.get("choices") or []

            if not choices:
                record_ai_usage(
                    project_name="OPENROUTER_FREE_AI",
                    section_name=section,
                    model_name=routed_model,
                    outcome="empty",
                    http_status=response.status_code,
                )
                last_error = RuntimeError(
                    f"OpenRouter routed to {routed_model}, but no generated text was returned."
                )
                if attempt == 0:
                    time.sleep(1)
                    continue
                break

            message = choices[0].get("message") or {}
            content = message.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict)
                )

            text = str(content or "").strip()

            if not text:
                for field in ("output_text", "reasoning_content"):
                    value = message.get(field)
                    if value:
                        text = str(value).strip()
                        if text:
                            break

            if not text:
                record_ai_usage(
                    project_name="OPENROUTER_FREE_AI",
                    section_name=section,
                    model_name=routed_model,
                    outcome="empty",
                    http_status=response.status_code,
                )
                last_error = RuntimeError(
                    f"OpenRouter routed to {routed_model}, but the response was empty."
                )
                if attempt == 0:
                    time.sleep(1)
                    continue
                break

            try:
                parsed = _extract_json(text)
            except Exception as exc:
                record_ai_usage(
                    project_name="OPENROUTER_FREE_AI",
                    section_name=section,
                    model_name=routed_model,
                    outcome="invalid_json",
                    http_status=response.status_code,
                )
                last_error = RuntimeError(
                    f"OpenRouter routed to {routed_model}, but it returned invalid JSON: {exc}"
                )
                if attempt == 0:
                    time.sleep(1)
                    continue
                break

            record_ai_usage(
                project_name="OPENROUTER_FREE_AI",
                section_name=section,
                model_name=routed_model,
                outcome="success",
                http_status=response.status_code,
            )
            print(
                f"[ToonScripture] {section}: OpenRouter free router completed via {routed_model}",
                flush=True,
            )
            return parsed

        except requests.Timeout as exc:
            last_error = exc
            record_ai_usage(
                project_name="OPENROUTER_FREE_AI",
                section_name=section,
                model_name=model,
                outcome="timeout",
                http_status=None,
            )
            if attempt == 0:
                continue

        except requests.RequestException as exc:
            last_error = exc
            record_ai_usage(
                project_name="OPENROUTER_FREE_AI",
                section_name=section,
                model_name=model,
                outcome="network_error",
                http_status=None,
            )
            if attempt == 0:
                continue

    raise RuntimeError(
        "OpenRouter Free AI could not complete this request after trying the free router. "
        f"Last error: {last_error}"
    )


def _synthesize_gemini_qwen(
    system_prompt,
    user_prompt,
    temperature,
    section,
    gemini_output,
    qwen_output,
):
    synthesis_system = """
You are ToonScripture's senior editorial director.
You receive two independent JSON candidates for the same production task:
one from Gemini and one from a free OpenRouter model.

Create one final superior result.

Rules:
- Follow the original requested schema exactly.
- Combine the strongest useful details from both candidates.
- Resolve disagreements using Scripture, historical plausibility, internal continuity,
  cinematic clarity, retention, and production usefulness.
- Prefer grounded, specific details over generic filler.
- Remove duplication.
- Do not invent unsupported factual claims.
- Preserve all important production constraints.
- Return valid JSON only.
"""

    synthesis_prompt = f"""
ORIGINAL SYSTEM INSTRUCTION:
{system_prompt}

ORIGINAL TASK:
{user_prompt}

GEMINI CANDIDATE:
{json.dumps(gemini_output, ensure_ascii=False, indent=2)}

OPENROUTER FREE MODEL CANDIDATE:
{json.dumps(qwen_output, ensure_ascii=False, indent=2)}

Produce the single best final JSON output for section: {section}.
"""

    return _call_gemini_only(
        synthesis_system,
        synthesis_prompt,
        temperature=min(float(temperature or 0.3), 0.3),
        section=section,
    )


def _call_gemini_only(system_prompt, user_prompt, temperature=0.3, section="general"):
    key_entries = _api_keys_for(section)
    if not key_entries:
        raise RuntimeError(
            "Gemini is not connected yet. Add the Gemini API keys in the deployment secrets."
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
        if model and model.startswith("gemini-") and model not in models:
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

    if section in {"treatment", "visual_bible"}:
        payload["tools"] = [{"google_search": {}}]

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

                    record_ai_usage(
                        project_name=key_entry["name"],
                        section_name=section,
                        model_name=model,
                        outcome="success" if response.ok else "error",
                        http_status=response.status_code,
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
                        print(
                            f"[ToonScripture] {section}: {model} is overloaded on "
                            f"{key_entry['name']}; trying the next model.",
                            flush=True,
                        )
                        break

                    if status == 400:
                        body = response.text.lower()
                        key_problem_markers = [
                            "api key not valid",
                            "api_key_invalid",
                            "permission denied",
                            "permission_denied",
                            "service disabled",
                            "service_disabled",
                            "has not been used",
                            "access not configured",
                        ]
                        if any(marker in body for marker in key_problem_markers):
                            print(
                                f"[ToonScripture] {section}: {key_entry['name']} rejected by Google; "
                                "trying reserved spare if available.",
                                flush=True,
                            )
                            fail_over_to_next_key = True
                            break

                        # A 400 can also be model/config related. Try the next model first.
                        print(
                            f"[ToonScripture] {section}: model {model} returned HTTP 400 on "
                            f"{key_entry['name']}: {response.text[:500]}",
                            flush=True,
                        )
                        break

                    if status == 404:
                        break

                    if status >= 500:
                        if attempt < 2:
                            time.sleep(2 * (attempt + 1))
                            continue
                        print(
                            f"[ToonScripture] {section}: {model} returned HTTP {status} on "
                            f"{key_entry['name']}; trying the next model.",
                            flush=True,
                        )
                        break

                    raise last_error

                except requests.Timeout as exc:
                    record_ai_usage(
                        project_name=key_entry["name"],
                        section_name=section,
                        model_name=model,
                        outcome="timeout",
                        http_status=None,
                    )
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    fail_over_to_next_key = True
                    break

                except requests.RequestException as exc:
                    record_ai_usage(
                        project_name=key_entry["name"],
                        section_name=section,
                        model_name=model,
                        outcome="network_error",
                        http_status=None,
                    )
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
        "Gemini could not complete this request with the configured project. "
        f"Last error: {last_error}"
    )


def call_json(system_prompt, user_prompt, temperature=0.3, section="general"):
    gemini_output = None
    qwen_output = None
    errors = []
    has_qwen = bool(_openrouter_key())

    print(
        f"[ToonScripture] {section}: OpenRouter configured = {has_qwen}",
        flush=True,
    )

    # Scene Production tries Qwen first so an exhausted Gemini scene project
    # cannot prevent the second model from participating.
    if section == "scenes" and has_qwen:
        try:
            print("[ToonScripture] scenes: calling OpenRouter Free Models", flush=True)
            qwen_output = _call_qwen_json(
                system_prompt,
                user_prompt,
                temperature=temperature,
                section=section,
            )
            print("[ToonScripture] scenes: OpenRouter Free Models completed", flush=True)
        except Exception as exc:
            errors.append(f"OpenRouter Free Models: {exc}")
            print(f"[ToonScripture] scenes: OpenRouter Free Models failed: {exc}", flush=True)

    try:
        gemini_output = _call_gemini_only(
            system_prompt,
            user_prompt,
            temperature=temperature,
            section=section,
        )
    except Exception as exc:
        errors.append(f"Gemini: {exc}")

    if section != "scenes" and has_qwen:
        try:
            print(
                f"[ToonScripture] {section}: calling OpenRouter Free Models",
                flush=True,
            )
            qwen_output = _call_qwen_json(
                system_prompt,
                user_prompt,
                temperature=temperature,
                section=section,
            )
            print(
                f"[ToonScripture] {section}: OpenRouter Free Models completed",
                flush=True,
            )
        except Exception as exc:
            errors.append(f"OpenRouter Free Models: {exc}")
            print(
                f"[ToonScripture] {section}: OpenRouter Free Models failed: {exc}",
                flush=True,
            )

    if gemini_output is not None and qwen_output is not None:
        try:
            return _synthesize_gemini_qwen(
                system_prompt,
                user_prompt,
                temperature,
                section,
                gemini_output,
                qwen_output,
            )
        except Exception as exc:
            errors.append(f"Synthesis: {exc}")
            return gemini_output

    if gemini_output is not None:
        return gemini_output

    if qwen_output is not None:
        return qwen_output

    if not has_qwen:
        errors.append(
            "OpenRouter key was not detected by the running Render service."
        )

    raise RuntimeError(
        "Neither Gemini nor OpenRouter Free Models could complete this step. "
        + " | ".join(errors)
    )


TREATMENT_SYSTEM = """
You are ToonScripture's Bible-story researcher, adaptation editor and YouTube story architect.

Build the story around viewer satisfaction, not gimmicks. The treatment must work for ANY requested
runtime. There is no universal ideal YouTube length, so use exactly the length needed to sustain value
without filler.

Research-backed story principles to apply:
- Treat the user's Bible reference as the PRIMARY STARTING SCOPE, never as the maximum research boundary.
- Use grounded Bible research to find additional canonical passages that materially clarify the story:
  parallel Gospel accounts, explicit cross-references, Old Testament background, prophecies explicitly
  identified as fulfilled in the New Testament, apostolic interpretation, covenant/background passages,
  and later passages that explain the significance of the event.
- Distinguish direct narrative evidence from explicit New Testament fulfillment/cross-reference,
  historical background, and traditional/theological connections. Do not present disputed typology
  as if it were an uncontested textual fact.
- Prefer Scripture itself and reliable cross-reference material over unsourced devotional claims.
- The title/thumbnail promise and the opening must match. The first 30 seconds must immediately confirm
  the viewer made the right click.
- Create a clear central dramatic question, then sustain curiosity, suspense or anticipation through
  cause-and-effect progression.
- Prioritize narrative transportation: concrete settings, understandable character goals, obstacles,
  consequences, emotional stakes and vivid sceneable moments.
- Do not flatten the story into chronology or event lists. Every beat must change the situation,
  deepen meaning, increase stakes, reveal something important or pay off an earlier question.
- Place compelling material early instead of saving all of the strongest moments for late in the video.
- Build emotional flow across the full experience, with at least one memorable peak and a strong ending.
- Avoid filler, repetition, generic sermon language and redundant explanation.
- Preserve scriptural accuracy. Separate scriptural facts, historically plausible interpretation and
  cinematic continuity decisions.

Return valid JSON only.
"""

SCRIPT_SYSTEM = """
You are ToonScripture's senior long-form YouTube Bible-story writer, story editor and retention engineer.

Write for the exact requested runtime, whether it is 4, 6, 8, 10, 12, 15 minutes or another length.
There is no default 10-minute structure.

Your job is to produce a FIRST-VISIBLE DRAFT that already performs like a polished final draft.

Before returning the script, silently complete this internal process in the SAME response:
1. Build a narrative spine from the approved treatment.
2. Draft the complete script.
3. Audit the draft against the retention rubric below.
4. Rewrite weak sections internally.
5. Return only the improved final script.

RETENTION RUBRIC:
- Promise match: opening immediately delivers the value implied by the story/title concept.
- First 30 seconds: specific, active, emotionally or intellectually compelling, with no throat-clearing.
- Dramatic question: the viewer understands what is at stake and what they are waiting to discover.
- Cause and effect: events feel connected rather than listed.
- Narrative transportation: concrete places, goals, obstacles, consequences, emotional responses and
  visualizable actions keep the viewer inside the story world.
- Curiosity / suspense: unresolved questions are opened naturally and paid off clearly.
- Progression: every section adds new value, changes the situation or increases stakes.
- Emotional flow: intensity rises and falls intentionally instead of staying flat.
- Clarity: chronology, time jumps, names, motives and theology are easy to follow.
- Specificity: prefer precise story moments over abstract summary language.
- Repetition control: do not repeat the same theological conclusion in different words.
- Sceneability: narration should readily translate into visual beats.
- Peak and ending: create a memorable emotional high point and a satisfying ending payoff.
- Runtime discipline: no filler added merely to hit duration.

WRITING RULES:
- Preserve Scripture and the approved treatment.
- Do not invent unsupported historical or theological claims.
- Family-friendly, cinematic and emotionally clear.
- Avoid generic sermon filler and rapid-fire event lists.
- Use transitions that bridge large time jumps.
- Keep dialogue sparse and purposeful unless directly supported or clearly framed as cinematic adaptation.
- Do not output an internal score or critique.

Return valid JSON only with exactly:
{
  "hook": "",
  "sections": [
    {"name":"", "purpose":"", "narration":"", "dialogue":[]}
  ],
  "closing": ""
}
"""

CRITIQUE_SYSTEM = """
You are ToonScripture's strict YouTube retention and storytelling auditor.

Score honestly. Do not inflate the score to satisfy a target.
A 95+ score means the script is genuinely exceptional, not merely competent.

Evaluate:
1. title/story promise alignment and opening delivery
2. first-30-second hook strength
3. central dramatic question and stakes
4. curiosity, suspense and anticipation
5. cause-and-effect progression
6. narrative transportation and character involvement
7. pacing and new-value density
8. emotional flow and escalation
9. clarity across chronology and transitions
10. specificity and sceneability
11. repetition/filler control
12. memorable peak and ending payoff
13. scriptural accuracy and responsible interpretation
14. suitability for the requested runtime

Penalize:
- event-list narration
- generic summary prose
- repeated theological conclusions
- unexplained time jumps
- hooks that delay the actual story
- weak middle sections
- CTAs or filler that interrupt the narrative before payoff

Return valid JSON only with:
score_100, strengths, problems, recommended_cuts, recommended_additions.
"""

RETENTION_REWRITE_SYSTEM = """
You are ToonScripture's senior long-form YouTube script doctor.
Rewrite the supplied Bible-story script to fix every retention problem identified by the critic.

Requirements:
- Preserve scriptural accuracy and the approved story arc.
- Preserve the requested runtime rather than simply making the script shorter.
- Strengthen the opening hook, pacing, emotional escalation, specificity, transitions and payoff.
- Remove repetition, list-like narration and generic summary language.
- Use sceneable, cinematic language.
- Keep chronology clear.
- Do not add unsupported theological or historical claims.
- Return the COMPLETE revised script, not notes.
- Return valid JSON only with exactly:
{
  "hook": "",
  "sections": [
    {"name":"", "purpose":"", "narration":"", "dialogue":[]}
  ],
  "closing": ""
}
"""

SCENE_SYSTEM = """
You are ToonScripture's scene planner and prompt engineer.
Turn one approved narration segment into an exact sequence of short Flow-ready clips.
Allowed clip lengths are ONLY 4, 5, 8, or 10 seconds.
Create exactly the requested number of clips, in narration order, and cover the entire supplied segment.
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
    target_minutes = float(p['target_minutes'])
    target_seconds = int(round(target_minutes * 60))
    channel_learning = channel_performance_learning()

    # Scale story density with runtime instead of forcing every episode into
    # the same number of beats.
    target_beats = max(5, min(18, round(target_minutes * 1.2)))

    prompt = f"""
STORY: {p['story_name']}
USER-SUPPLIED PRIMARY BIBLE REFERENCE: {p['bible_reference']}
TARGET RUNTIME: {target_minutes:g} minutes ({target_seconds} seconds)
TARGET STORY BEATS: approximately {target_beats}, adjusted naturally for the material

SCRIPTURE RESEARCH REQUIREMENT:
Research beyond the supplied reference before shaping the story.
The supplied reference is authoritative starting scope, not a restriction.

Find additional relevant canonical passages and classify each one as one of:
- parallel_narrative
- explicit_nt_fulfillment_or_cross_reference
- old_testament_background
- apostolic_interpretation
- theological_context
- traditional_connection_needing_caution

For each added passage, explain briefly why it is relevant and whether it should actually influence
the narration. Do not pad the list with weak connections. Quality matters more than quantity.

STORY-UNIVERSE RESEARCH REQUIREMENT:
Also research the wider story universe around the selected subject. Look for:
- distinct episodes from the person's life that deserve separate videos
- supporting characters with meaningful connected stories
- cities, regions, temples, kingdoms, journeys and recurring locations that can sustain their own episodes
- before/after stories that explain how the current story came to happen or what followed it
- natural Part 1 / Part 2 / Part 3 structures where one long life or narrative should not be crushed into one video
- connected canonical stories that share a place, conflict, family line, ministry period or major event

Do NOT force everything into one episode. If the subject is broad (for example Jesus, Moses, David,
Paul, Jerusalem, Babylon), propose a coherent multi-episode series. Each episode must have its own
dramatic question, scripture scope and reason to exist. Avoid duplicate episodes that tell the same story.

CHANNEL PERFORMANCE LEARNING:
{json.dumps(channel_learning, indent=2)}

Use channel learning carefully:
- Treat it as evidence, not a rigid formula.
- If confidence is "early", do not generalize strongly from one or two videos.
- If confidence is "emerging", use patterns as hypotheses.
- If confidence is "useful" or "strong", deliberately preserve what repeatedly works and avoid repeated failure patterns.
- Never sacrifice scriptural accuracy or story logic just to mimic a past video's metrics.

Design the treatment so the full episode sustains attention at THIS runtime without filler.

Return:
{{
  "core_story": "",
  "viewer_promise": "",
  "central_dramatic_question": "",
  "first_30_seconds": {{
    "opening_image_or_moment": "",
    "hook": "",
    "promise_confirmation": "",
    "question_or_tension_opened": ""
  }},
  "scriptural_anchor": [],
  "researched_scripture_references": [
    {
      "reference": "",
      "category": "",
      "relevance": "",
      "use_in_story": "",
      "confidence": "high|medium|caution"
    }
  ],
  "story_universe": {
    "character_threads": [
      {
        "subject": "",
        "why_it_matters": "",
        "references": []
      }
    ],
    "place_threads": [
      {
        "place": "",
        "why_it_matters": "",
        "references": []
      }
    ],
    "supporting_character_threads": [
      {
        "subject": "",
        "why_it_matters": "",
        "references": []
      }
    ]
  },
  "series_opportunities": [
    {
      "series_title": "",
      "episode_title": "",
      "part_number": 1,
      "focus": "",
      "bible_references": [],
      "key_characters": [],
      "key_places": [],
      "why_this_deserves_its_own_episode": "",
      "recommended_runtime_minutes": 8
    }
  ],
  "historical_context": [],
  "cinematic_interpretations": [],
  "emotional_arc": "",
  "story_beats": [
    {{
      "beat": "",
      "purpose": "",
      "new_value": "",
      "stakes_change": "",
      "curiosity_or_suspense": "",
      "payoff_or_transition": ""
    }}
  ],
  "curiosity_loops": [
    {{"open": "", "payoff": ""}}
  ],
  "emotional_peaks": [],
  "top_moment_candidates": [],
  "accuracy_risks": [],
  "ending_payoff": "",
  "anti_filler_notes": []
}}
"""
    out = call_json(TREATMENT_SYSTEM, prompt, 0.25, section="treatment")
    save_json(project_id, "treatment_json", out, "treatment_ready")
    return out


def draft_script(project_id):
    p = get_project(project_id)
    treatment = load_json(p, "treatment_json", {})
    target_minutes = float(p['target_minutes'])
    channel_learning = channel_performance_learning()

    # Spoken narration varies naturally by dramatic intensity. Use a flexible
    # range instead of pretending every minute should contain the same number
    # of words.
    min_words = int(round(target_minutes * 125))
    target_words = int(round(target_minutes * 140))
    max_words = int(round(target_minutes * 155))
    section_target = max(4, min(16, round(target_minutes * 0.9)))

    prompt = f"""
TARGET RUNTIME: {target_minutes:g} minutes
NARRATION RANGE: about {min_words}-{max_words} words
WORKING TARGET: about {target_words} words
EXPECTED MAJOR SECTIONS: approximately {section_target}, adjusted naturally for the story

APPROVED TREATMENT:
{json.dumps(treatment, indent=2)}

CHANNEL PERFORMANCE LEARNING:
{json.dumps(channel_learning, indent=2)}

Apply channel learning only when the data actually supports it. Do not overfit a single video's result.

FIRST-VISIBLE-DRAFT QUALITY GATE:
This draft should be capable of scoring 95+ under the strict retention rubric without relying on
later cleanup.

Before returning it, silently audit and revise:
- Does the first 30 seconds immediately fulfill the viewer promise?
- Is there a clear dramatic question or tension the viewer wants resolved?
- Does every section introduce new value rather than paraphrase the previous one?
- Are chronology and time jumps effortless to follow?
- Are suspense and curiosity created by the actual story rather than artificial clickbait?
- Are there concrete visual moments that increase narrative transportation?
- Is the strongest material brought forward instead of unnecessarily delayed?
- Is the middle as purposeful as the beginning and ending?
- Is there a memorable emotional peak?
- Does the ending resolve the central promise and leave a strong final impression?
- Is the script free of filler, generic sermon language and event-list narration?

Return only the final script JSON.
"""
    out = call_json(SCRIPT_SYSTEM, prompt, 0.35, section="script")
    save_json(project_id, "script_json", out, "script_ready")
    return out


def critique_script(project_id, target_score=95, max_rewrite_rounds=2):
    """
    Review the script and enforce ToonScripture's retention quality gate.

    If the honest review is below target_score, automatically rewrite the
    complete script from the critique and review it again. We cap automatic
    rewrites so one click cannot create an uncontrolled chain of API calls.
    The best script/review found is saved even if the target is not reached.
    """
    p = get_project(project_id)
    script = load_json(p, "script_json", {})

    if not script:
        raise RuntimeError("Write the script before running the retention review.")

    best_script = script
    best_review = None
    best_score = -1
    attempts = []

    for round_index in range(max_rewrite_rounds + 1):
        treatment = load_json(p, "treatment_json", {})
        accuracy_context = {
            "primary_reference": p.get("bible_reference"),
            "scriptural_anchor": treatment.get("scriptural_anchor", []),
            "researched_scripture_references": treatment.get(
                "researched_scripture_references",
                [],
            ),
        }

        review = call_json(
            CRITIQUE_SYSTEM,
            (
                "SCRIPTURAL ACCURACY CONTEXT:\n"
                + json.dumps(accuracy_context, indent=2)
                + "\n\nSCRIPT TO REVIEW:\n"
                + json.dumps(best_script, indent=2)
            ),
            0.15,
            section="retention",
        )

        try:
            score = int(round(float(review.get("score_100", 0) or 0)))
        except Exception:
            score = 0

        attempts.append({
            "round": round_index + 1,
            "score": score,
        })

        if score > best_score:
            best_score = score
            best_review = review

        if score >= target_score:
            break

        if round_index >= max_rewrite_rounds:
            break

        rewrite_prompt = f"""
TARGET RUNTIME: {p['target_minutes']} minutes
QUALITY TARGET: {target_score}/100 or better

CURRENT SCRIPT:
{json.dumps(best_script, indent=2)}

RETENTION REVIEW:
{json.dumps(review, indent=2)}

Rewrite the complete script so the specific problems above are fixed.
Do not game the score and do not merely mention the fixes. Actually rewrite the narration.
"""

        revised = call_json(
            RETENTION_REWRITE_SYSTEM,
            rewrite_prompt,
            0.25,
            section="script",
        )

        if revised:
            best_script = revised
            save_json(project_id, "script_json", best_script, "script_ready")

    if best_review is None:
        raise RuntimeError("The retention review returned no usable result.")

    best_review["quality_target"] = target_score
    best_review["quality_gate_passed"] = best_score >= target_score
    best_review["review_attempts"] = attempts
    best_review["automatic_rewrite_rounds"] = max(0, len(attempts) - 1)

    save_json(project_id, "critique_json", best_review)
    return best_review


def _fit_flow_durations(raw_durations, target_seconds):
    allowed = (4, 5, 8, 10)
    if not raw_durations:
        return []

    states = {0: (0, [])}

    for raw in raw_durations:
        try:
            raw_value = int(raw)
        except Exception:
            raw_value = 8

        next_states = {}
        for total, (cost, path) in states.items():
            for duration in allowed:
                new_total = total + duration
                if new_total > target_seconds + 10:
                    continue

                new_cost = cost + abs(duration - raw_value)
                current = next_states.get(new_total)

                if current is None or new_cost < current[0]:
                    next_states[new_total] = (
                        new_cost,
                        path + [duration],
                    )

        states = next_states

    if not states:
        return [
            min(allowed, key=lambda value: abs(value - int(raw or 8)))
            for raw in raw_durations
        ]

    best_total = min(
        states,
        key=lambda total: (
            abs(total - target_seconds),
            states[total][0],
        ),
    )
    return states[best_total][1]


def plan_scenes(project_id):
    p = get_project(project_id)
    script = load_json(p, "script_json", {})
    bible = load_json(p, "character_bible_json", {})

    target_seconds = int(round(float(p["target_minutes"]) * 60))
    timing_source = "episode target"

    saved_audio = list_project_assets(project_id, "narration_audio")
    if saved_audio:
        metadata = saved_audio[0].get("metadata_json") or {}
        audio_seconds = metadata.get("duration_seconds")
        try:
            audio_seconds = int(round(float(audio_seconds)))
        except Exception:
            audio_seconds = 0

        if audio_seconds > 0:
            target_seconds = audio_seconds
            timing_source = "narration audio"

    narration_parts = []
    if script.get("hook"):
        narration_parts.append(("Opening hook", script["hook"]))

    for section in script.get("sections", []):
        text = section.get("narration") or ""
        dialogue = section.get("dialogue") or []
        if isinstance(dialogue, list):
            dialogue_text = " ".join(
                line if isinstance(line, str)
                else str(
                    line.get("text")
                    or line.get("line")
                    or line.get("dialogue")
                    or ""
                )
                for line in dialogue
            )
            text = (text + " " + dialogue_text).strip()

        if text:
            narration_parts.append(
                (section.get("name") or "Story section", text)
            )

    if script.get("closing"):
        narration_parts.append(("Closing", script["closing"]))

    # One AI request for the entire episode. The previous per-section approach
    # caused 8-12 long network calls and made Streamlit appear frozen.
    scene_count = max(1, round(target_seconds / 8))

    full_narration = "\n\n".join(
        f"{name}:\n{text}"
        for name, text in narration_parts
    )

    prompt = f"""
STORY: {p['story_name']}
FULL EPISODE RUNTIME: {target_seconds} seconds
TIMING SOURCE: {timing_source}

FULL APPROVED NARRATION, IN ORDER:
{full_narration}

CHARACTER/WORLD BIBLE:
{json.dumps(bible, indent=2)}

Create EXACTLY {scene_count} Flow-ready clips for the WHOLE EPISODE in narration order.

Important:
- Every part of the narration must be visually covered.
- duration_seconds may ONLY be 4, 5, 8, or 10.
- Use start_state -> dominant_action -> end_state for every clip.
- Keep recurring characters, costumes, locations and props consistent with the Visual Bible.
- Use shorter clips for fast action and longer clips for reflective or establishing beats.
- Do not merge distant story moments into one clip.
- Return one JSON object with a single scenes array.
"""

    out = call_json(
        SCENE_SYSTEM,
        prompt,
        0.2,
        section="scenes",
    )

    scenes = out.get("scenes", []) or []
    if not scenes:
        raise RuntimeError("The scene planner returned no scenes.")

    # Normalize numbering and Flow-supported lengths.
    for index, scene in enumerate(scenes, start=1):
        duration = int(scene.get("duration_seconds") or 8)
        scene["duration_seconds"] = min(
            (4, 5, 8, 10),
            key=lambda value: abs(value - duration),
        )
        scene["scene_number"] = index
        scene.setdefault("production_status", "not_started")

    fitted_durations = _fit_flow_durations(
        [scene.get("duration_seconds") or 8 for scene in scenes],
        target_seconds,
    )

    for scene, duration in zip(scenes, fitted_durations):
        scene["duration_seconds"] = duration

    planned_seconds = sum(
        int(scene.get("duration_seconds") or 0)
        for scene in scenes
    )

    out = {
        "target_runtime_seconds": target_seconds,
        "timing_source": timing_source,
        "allowed_clip_lengths": [4, 5, 8, 10],
        "planned_runtime_seconds": planned_seconds,
        "runtime_difference_seconds": planned_seconds - target_seconds,
        "scenes": scenes,
    }

    save_json(project_id, "scenes_json", out, "scenes_ready")
    return out

def make_package(project_id):
    p = get_project(project_id)
    script = load_json(p, "script_json", {})
    prompt = f"STORY: {p['story_name']}\nSCRIPT:\n{json.dumps(script, indent=2)}"
    out = call_json(PACKAGE_SYSTEM, prompt, 0.55, section="youtube")
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
""", 0.2, section="visual_bible")

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
""", 0.2, section="visual_bible")

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
""", 0.2, section="visual_bible")

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
""", 0.2, section="visual_bible")

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
    key, _ = _api_key_for("tts")
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
    key, _ = _api_key_for("tts")
    if not key:
        raise RuntimeError(
            "The TTS Gemini project is not configured yet."
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
    key, _ = _api_key_for("vision")
    if not key:
        raise RuntimeError(
            "The visual review Gemini project is not configured yet."
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
