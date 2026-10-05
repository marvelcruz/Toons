import os
import json
import streamlit as st

from db import (
    init_db, list_projects, get_project, create_project, load_json,
    catalog_summary, list_catalog_people, list_series, link_project,
    import_spreadsheet,
)
from workflow import (
    develop_treatment, draft_script, critique_script,
    build_character_bible, plan_scenes, make_package,
)

st.set_page_config(page_title="ToonScripture OS", page_icon="🎬", layout="wide")
init_db()


def pretty(value):
    return str(value or "").replace("_", " ").title()


def safe_json(data):
    if data:
        with st.expander("See full details"):
            st.json(data)


def render_script(script):
    if not script:
        st.info("The script has not been created yet.")
        return
    hook = script.get("hook")
    if hook:
        st.markdown("### Opening")
        st.write(hook)
    for i, section in enumerate(script.get("sections", []), 1):
        name = section.get("name") or f"Section {i}"
        with st.expander(name, expanded=i == 1):
            if section.get("purpose"):
                st.caption(section["purpose"])
            if section.get("narration"):
                st.write(section["narration"])
            dialogue = section.get("dialogue")
            if dialogue:
                st.markdown("**Dialogue**")
                for line in dialogue if isinstance(dialogue, list) else [dialogue]:
                    st.write(line)


def stage_status(project):
    return [
        ("Treatment", bool(project.get("treatment_json"))),
        ("Script", bool(project.get("script_json"))),
        ("Review", bool(project.get("critique_json"))),
        ("Visual Bible", bool(project.get("character_bible_json"))),
        ("Scenes", bool(project.get("scenes_json"))),
        ("YouTube Pack", bool(project.get("package_json"))),
    ]


def current_project_selector():
    projects = list_projects()
    if not projects:
        return None

    labels = {
        p["id"]: f"{p['story_name']} · {p['target_minutes']} min"
        for p in projects
    }
    ids = [p["id"] for p in projects]

    preferred = st.session_state.get("project_id")
    index = ids.index(preferred) if preferred in ids else 0
    chosen = st.selectbox(
        "Current episode",
        ids,
        index=index,
        format_func=lambda pid: labels[pid],
        label_visibility="collapsed",
    )
    st.session_state.project_id = chosen
    return get_project(chosen)


# -------------------------
# SIDEBAR
# -------------------------
with st.sidebar:
    st.markdown("# ToonScripture")
    st.caption("Cinematic Bible Story Studio")
    st.divider()

    project = current_project_selector()

    if project:
        st.markdown(f"**{project['story_name']}**")
        st.caption(f"{project['bible_reference']} · {project['target_minutes']} min")
        completed = sum(1 for _, ok in stage_status(project) if ok)
        st.progress(completed / 6, text=f"{completed}/6 production stages ready")

        with st.expander("Episode details"):
            st.write("Type:", pretty(project["format"]))
            st.write("Status:", pretty(project["status"]))
            st.write("Project:", project["id"])
    else:
        st.caption("No episode created yet.")

    st.divider()
    try:
        from workflow import _api_key
        if _api_key():
            st.success("Gemini connected", icon="✅")
        else:
            st.warning("Gemini key not added yet")
    except Exception:
        pass


# -------------------------
# HEADER
# -------------------------
st.title("ToonScripture OS")
st.caption("Choose the story → build the episode → lock the look → create the scenes → package for YouTube")

tabs = st.tabs(["Home", "Episode", "Visual Bible", "Production", "Publish"])


# -------------------------
# HOME
# -------------------------
with tabs[0]:
    st.header("What do you want to make next?")

    summary = catalog_summary()

    if summary["people_total"] == 0:
        st.info(
            "Your story catalogue is not in this database yet. "
            "Upload the ToonScripture planning spreadsheet once and the app will store it in the database."
        )
        uploaded = st.file_uploader(
            "Upload Bible cinematic production spreadsheet",
            type=["xlsx"],
            key="catalog_upload",
        )
        if uploaded and st.button("Import my catalogue", type="primary"):
            with st.spinner("Importing your catalogue..."):
                result = import_spreadsheet(uploaded.getvalue())
            st.success(
                f"Imported {result['people_total']} people and {result['series_total']} series."
            )
            st.rerun()
    else:
        a, b, c, d = st.columns(4)
        a.metric("Stories / characters", summary["people_total"])
        b.metric("High priority", summary["high_priority"])
        c.metric("Women", summary["women_total"])
        d.metric("Men", summary["men_total"])

        st.markdown("### Find a story")
        search = st.text_input(
            "Search",
            placeholder="Try Daniel, Esther, Moses, lions' den...",
            label_visibility="collapsed",
        )

        with st.expander("Optional filters"):
            c1, c2 = st.columns(2)
            with c1:
                priority = st.selectbox("Priority", ["All", "High", "Medium", "Low"])
            with c2:
                people_type = st.selectbox("People", ["All", "Men", "Women"])

        entity_type = ""
        if people_type == "Men":
            entity_type = "man"
        elif people_type == "Women":
            entity_type = "woman"

        rows = list_catalog_people(
            search=search,
            priority="" if priority == "All" else priority,
            entity_type=entity_type,
            limit=40,
        )

        if not rows:
            st.warning("No catalogue entry matches that search.")
        else:
            selected_id = st.selectbox(
                "Choose a story / character",
                [r["id"] for r in rows],
                format_func=lambda cid: next(
                    f"{r['name']} · {r.get('bible_references') or 'Bible reference not set'}"
                    for r in rows if r["id"] == cid
                ),
            )
            selected = next(r for r in rows if r["id"] == selected_id)

            st.markdown(f"## {selected['name']}")
            left, right = st.columns([2, 1])
            with left:
                if selected.get("story_role"):
                    st.write(selected["story_role"])
                if selected.get("bible_references"):
                    st.markdown(f"**Bible:** {selected['bible_references']}")
                if selected.get("primary_environment"):
                    st.markdown(f"**Main setting:** {selected['primary_environment']}")
                if selected.get("youtube_hook"):
                    st.markdown(f"**YouTube angle:** {selected['youtube_hook']}")
                if selected.get("playlist_series"):
                    st.markdown(f"**Series:** {selected['playlist_series']}")
                if selected.get("notes"):
                    with st.expander("Planning note"):
                        st.write(selected["notes"])
            with right:
                st.metric("Priority", selected.get("priority") or "—")
                if selected.get("cinematic_score") is not None:
                    st.metric("Cinematic score", f"{selected['cinematic_score']:.1f}")

            st.markdown("### Start an episode")
            default_title = selected["name"]
            episode_title = st.text_input(
                "Episode title",
                value=default_title,
                help="You can make the title specific, e.g. Daniel in the Lions' Den.",
            )
            episode_reference = st.text_input(
                "Bible reference",
                value=selected.get("bible_references") or "",
            )
            runtime = st.slider("Target runtime", 3.0, 20.0, 8.0, 0.5)

            if st.button("Start this episode", type="primary", use_container_width=True):
                pid = create_project(episode_title, episode_reference, runtime, "long_form")
                link_project(pid, person_id=selected_id, episode_title=episode_title)
                st.session_state.project_id = pid
                st.success("Episode created. Open the Episode tab to start the treatment.")
                st.rerun()

        series = list_series()
        if series:
            with st.expander("Browse series / playlists"):
                for item in series:
                    st.markdown(f"**{item['series_name']}**")
                    if item.get("core_concept"):
                        st.write(item["core_concept"])
                    if item.get("best_starter_episodes"):
                        st.caption("Starter episodes: " + str(item["best_starter_episodes"]))
                    st.divider()

    with st.expander("Create an episode manually"):
        manual_title = st.text_input("Story title", key="manual_title")
        manual_ref = st.text_input("Bible reference", key="manual_ref")
        manual_minutes = st.number_input(
            "Target minutes", min_value=2.0, max_value=30.0, value=8.0, step=0.5
        )
        if st.button("Create episode", key="manual_create"):
            if not manual_title.strip():
                st.error("Enter a story title first.")
            else:
                pid = create_project(manual_title, manual_ref, manual_minutes, "long_form")
                st.session_state.project_id = pid
                st.rerun()


# Refresh current project after possible creation
project = get_project(st.session_state.get("project_id")) if st.session_state.get("project_id") else None


# -------------------------
# EPISODE
# -------------------------
with tabs[1]:
    if not project:
        st.info("Choose or create an episode from Home first.")
    else:
        st.header(project["story_name"])
        st.caption(f"{project['bible_reference']} · target {project['target_minutes']} minutes")

        statuses = stage_status(project)
        cols = st.columns(6)
        for col, (label, done) in zip(cols, statuses):
            col.markdown(("✅ " if done else "○ ") + label)

        st.divider()

        st.subheader("1. Story treatment")
        if st.button(
            "Create treatment" if not project.get("treatment_json") else "Regenerate treatment",
            key="make_treatment",
        ):
            with st.spinner("Researching and shaping the story..."):
                develop_treatment(project["id"])
            st.rerun()

        treatment = load_json(project, "treatment_json", {})
        if treatment:
            if treatment.get("opening_hook"):
                st.markdown("**Opening idea**")
                st.write(treatment["opening_hook"])
            if treatment.get("emotional_arc"):
                st.markdown("**Emotional arc**")
                st.write(treatment["emotional_arc"])
            beats = treatment.get("story_beats", [])
            if beats:
                st.markdown("**Story beats**")
                for beat in beats:
                    st.write("•", beat)
            safe_json(treatment)

        st.divider()

        st.subheader("2. Script")
        if not treatment:
            st.caption("Create the treatment first.")
        else:
            if st.button(
                "Write script" if not project.get("script_json") else "Regenerate script",
                key="make_script",
            ):
                with st.spinner("Writing the episode..."):
                    draft_script(project["id"])
                st.rerun()

        script = load_json(project, "script_json", {})
        render_script(script)

        st.divider()

        st.subheader("3. Retention review")
        if script:
            if st.button(
                "Review the script" if not project.get("critique_json") else "Review again",
                key="make_critique",
            ):
                with st.spinner("Checking pacing and retention..."):
                    critique_script(project["id"])
                st.rerun()

        critique = load_json(project, "critique_json", {})
        if critique:
            score = critique.get("score_100")
            if score is not None:
                st.metric("Retention score", f"{score}/100")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**What works**")
                for x in critique.get("strengths", []):
                    st.write("•", x)
            with c2:
                st.markdown("**What needs work**")
                for x in critique.get("problems", []):
                    st.write("•", x)
            safe_json(critique)


# -------------------------
# VISUAL BIBLE
# -------------------------
with tabs[2]:
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("script_json"):
        st.info("Finish the script first. The visual bible is built from the approved story.")
    else:
        st.header("Visual Bible")
        st.caption(
            "This locks the look of recurring people, uniforms, creatures, locations and props "
            "before scene generation."
        )

        if st.button(
            "Build visual bible" if not project.get("character_bible_json") else "Rebuild visual bible",
            type="primary",
        ):
            with st.spinner("Building characters, groups, locations and props in four smaller passes..."):
                build_character_bible(project["id"])
            st.rerun()

        bible = load_json(project, "character_bible_json", {})
        if bible:
            sub = st.tabs(["Main characters", "Supporting", "Groups / uniforms", "Locations", "Props"])

            sections = [
                ("characters", "Main character"),
                ("supporting_characters", "Supporting character"),
                ("character_groups", "Group"),
                ("locations", "Location"),
                ("props", "Prop"),
            ]

            for tab, (key, label) in zip(sub, sections):
                with tab:
                    items = bible.get(key, [])
                    if not items:
                        st.caption(f"No {label.lower()} entries.")
                        continue
                    names = [x.get("name") or f"{label} {i+1}" for i, x in enumerate(items)]
                    name = st.selectbox(label, names, key=f"{project['id']}_{key}")
                    item = items[names.index(name)]
                    st.markdown(f"### {name}")

                    if key in ("characters", "supporting_characters"):
                        if item.get("role"):
                            st.caption(item["role"])
                        if item.get("master_character_prompt"):
                            st.markdown("**Reference-image prompt**")
                            st.code(item["master_character_prompt"], wrap_lines=True)
                        if item.get("identity_lock"):
                            st.markdown("**Identity lock**")
                            st.code(item["identity_lock"], wrap_lines=True)
                    elif key == "character_groups":
                        if item.get("story_function"):
                            st.caption(item["story_function"])
                        if item.get("master_group_prompt"):
                            st.markdown("**Group reference prompt**")
                            st.code(item["master_group_prompt"], wrap_lines=True)
                        if item.get("group_identity_lock"):
                            st.markdown("**Group / uniform lock**")
                            st.code(item["group_identity_lock"], wrap_lines=True)
                        if item.get("allowed_individual_variation"):
                            st.markdown("**Allowed variation**")
                            for x in item["allowed_individual_variation"]:
                                st.write("•", x)
                    elif key == "locations":
                        if item.get("master_environment_prompt"):
                            st.markdown("**Environment reference prompt**")
                            st.code(item["master_environment_prompt"], wrap_lines=True)
                        if item.get("environment_lock"):
                            st.markdown("**Environment lock**")
                            st.code(item["environment_lock"], wrap_lines=True)
                    else:
                        if item.get("master_prop_prompt"):
                            st.markdown("**Prop reference prompt**")
                            st.code(item["master_prop_prompt"], wrap_lines=True)

                    with st.expander("All visual details"):
                        st.json(item)


# -------------------------
# PRODUCTION
# -------------------------
with tabs[3]:
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("character_bible_json"):
        st.info("Build the Visual Bible first so scene prompts can preserve continuity.")
    else:
        st.header("Scene Production")
        st.caption("Every scene uses Start → Action → End logic.")

        if st.button(
            "Build scenes" if not project.get("scenes_json") else "Rebuild scenes",
            type="primary",
        ):
            with st.spinner("Breaking the episode into production scenes..."):
                plan_scenes(project["id"])
            st.rerun()

        scene_data = load_json(project, "scenes_json", {})
        scenes = scene_data.get("scenes", [])
        if scenes:
            labels = [
                f"Scene {s.get('scene_number', i+1)} · {s.get('scene_title', 'Untitled')}"
                for i, s in enumerate(scenes)
            ]
            label = st.selectbox("Choose scene", labels)
            scene = scenes[labels.index(label)]

            st.markdown(f"## {label}")
            if scene.get("narration"):
                st.write(scene["narration"])

            a, b, c = st.columns(3)
            with a:
                st.markdown("**START**")
                st.write(scene.get("start_state") or "—")
            with b:
                st.markdown("**ACTION**")
                st.write(scene.get("dominant_action") or "—")
            with c:
                st.markdown("**END**")
                st.write(scene.get("end_state") or "—")

            if scene.get("physical_constraints"):
                with st.expander("Physical / spatial rules"):
                    for x in scene.get("physical_constraints", []):
                        st.write("•", x)

            st.markdown("### Frame prompt")
            st.code(scene.get("frame_prompt") or "", wrap_lines=True)

            st.markdown("### Video prompt")
            st.code(scene.get("video_prompt") or "", wrap_lines=True)

            negatives = scene.get("negative_constraints", [])
            if negatives:
                with st.expander("Do not allow"):
                    for x in negatives:
                        st.write("•", x)


# -------------------------
# PUBLISH
# -------------------------
with tabs[4]:
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("script_json"):
        st.info("Finish the script first.")
    else:
        st.header("YouTube Package")

        if st.button(
            "Create YouTube package" if not project.get("package_json") else "Regenerate package",
            type="primary",
        ):
            with st.spinner("Creating titles, thumbnail direction and description..."):
                make_package(project["id"])
            st.rerun()

        package = load_json(project, "package_json", {})
        if package:
            title = package.get("strongest_recommended_title")
            if isinstance(title, dict):
                title = title.get("title")
            if title:
                st.markdown("### Recommended title")
                st.success(title)

            options = package.get("title_options", [])
            if options:
                with st.expander("Other title ideas"):
                    for option in options:
                        st.write("•", option)

            thumb = package.get("strongest_thumbnail_recommendation")
            if thumb:
                st.markdown("### Thumbnail direction")
                if isinstance(thumb, dict):
                    st.json(thumb)
                else:
                    st.write(thumb)

            description = package.get("youtube_description")
            if description:
                st.markdown("### Description")
                st.code(description, wrap_lines=True)

            comment = package.get("pinned_comment")
            if comment:
                st.markdown("### Pinned comment")
                st.code(comment, wrap_lines=True)
