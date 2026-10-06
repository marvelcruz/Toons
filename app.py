import json
import streamlit as st

from db import (
    init_db,
    list_projects,
    get_project,
    create_project,
    load_json,
    catalog_summary,
    catalog_progress_summary,
    set_catalog_production_status,
    list_catalog_people,
    list_series,
    link_project,
    import_spreadsheet,
    seed_catalog_if_empty,
    save_reference_asset,
    get_reference_asset,
    save_project_asset,
    list_project_assets,
    signed_asset_url,
    save_episode_metrics,
    list_episode_metrics,
    using_supabase,
)
from workflow import (
    develop_treatment,
    draft_script,
    critique_script,
    build_character_bible,
    plan_scenes,
    make_package,
    _api_key,
    _api_key_count,
    _api_key_names,
    narration_text,
    list_tts_voices,
    generate_tts_bytes,
    review_scene_frame,
)
from prompt_composer import compose_scene_package, reference_summary

st.set_page_config(
    page_title="ToonScripture OS",
    page_icon="🎬",
    layout="wide",
)

init_db()


# =========================================================
# CLOUD WORKSPACE
# =========================================================

if using_supabase():
    try:
        seed_catalog_if_empty()
    except Exception:
        st.warning(
            "Your workspace opened, but the story catalogue could not be prepared automatically. "
            "You can still upload the planning spreadsheet from Home."
        )


# =========================================================
# HELPERS
# =========================================================

def project_progress(project):
    checks = [
        bool(project.get("treatment_json")),
        bool(project.get("script_json")),
        bool(project.get("critique_json")),
        bool(project.get("character_bible_json")),
        bool(project.get("scenes_json")),
        bool(project.get("package_json")),
    ]
    return sum(checks), len(checks)


def next_step(project):
    if not project:
        return "Choose a story and create an episode."
    if not project.get("treatment_json"):
        return "Create the story treatment."
    if not project.get("script_json"):
        return "Write the narration script."
    if not project.get("critique_json"):
        return "Run the retention review."
    if not project.get("character_bible_json"):
        return "Build the Visual Bible so characters and locations stay consistent."
    if not project.get("scenes_json"):
        return "Break the episode into production scenes."
    if not project.get("package_json"):
        return "Create the YouTube title, thumbnail direction and description."
    return "This episode is fully prepared for production and publishing."


def go_to_story_step(value):
    st.session_state["story_step"] = value


def go_to_main_section(value):
    st.session_state["main_section"] = value


def render_project_card(project):
    if not project:
        st.info("No episode selected yet.")
        return

    done, total = project_progress(project)

    st.markdown(f"### {project['story_name']}")
    st.caption(
        f"{project.get('bible_reference') or 'Bible reference not set'} · "
        f"{project.get('target_minutes', 0)} min"
    )
    st.progress(done / total, text=f"{done} of {total} preparation stages complete")

    st.markdown("**What should I do next?**")
    st.write(next_step(project))


def show_script(script):
    if not script:
        st.info("The script has not been written yet.")
        return

    if script.get("hook"):
        st.markdown("## Opening hook")
        st.write(script["hook"])
        st.divider()

    sections = script.get("sections", [])
    for i, section in enumerate(sections):
        title = section.get("name") or f"Section {i + 1}"
        st.markdown(f"## {title}")

        if section.get("purpose"):
            st.caption(section["purpose"])

        if section.get("narration"):
            st.write(section["narration"])

        dialogue = section.get("dialogue")
        if dialogue:
            st.markdown("**Dialogue**")
            for line in dialogue if isinstance(dialogue, list) else [dialogue]:
                st.write(line)

        st.divider()

    if script.get("closing"):
        st.markdown("## Closing")
        st.write(script["closing"])


def current_project():
    projects = list_projects()
    if not projects:
        return None

    ids = [p["id"] for p in projects]
    labels = {
        p["id"]: f"{p['story_name']} · {p.get('target_minutes', 0)} min"
        for p in projects
    }

    preferred = st.session_state.get("project_id")
    index = ids.index(preferred) if preferred in ids else 0

    if len(projects) == 1:
        chosen = ids[0]
    else:
        chosen = st.selectbox(
            "Switch episode",
            ids,
            index=index,
            format_func=lambda pid: labels[pid],
            help="Choose another episode to continue working on.",
        )

    st.session_state.project_id = chosen
    return get_project(chosen)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("# 🎬 ToonScripture")
    st.caption("Cinematic Bible Story Studio")
    st.divider()

    project = current_project()

    st.markdown("### Current episode")

    if project:
        done, total = project_progress(project)
        st.markdown(f"**{project['story_name']}**")
        st.caption(
            f"{project.get('bible_reference') or 'Bible reference not set'} · "
            f"{project.get('target_minutes', 0)} min"
        )
        st.progress(done / total)
        st.caption(f"{done} of {total} preparation stages complete")
        st.caption(f"Next: {next_step(project)}")
    else:
        st.caption("No episode yet.")
        st.caption("Create your first episode from Home.")

    st.divider()

    with st.expander("⚙️ Settings"):
        st.caption(
            "Most people will not need to change anything here."
        )

        if _api_key():
            count = _api_key_count()
            st.success("AI tools are connected", icon="✅")
            if count > 1:
                st.caption(
                    f"1 primary Gemini project + {count - 1} backup project"
                    + ("s" if count - 1 != 1 else "")
                )

                names = _api_key_names()
                pretty = {"GEMINI_API_KEY": "Default project"}
                for letter in "ABCDEFGHI":
                    pretty[f"GEMINI_API_KEY_{letter}"] = f"Project {letter}"

                selected_name = st.selectbox(
                    "Primary AI project",
                    names,
                    index=0,
                    format_func=lambda name: pretty.get(name, name),
                    help=(
                        "Choose which configured Gemini project ToonScripture should use first. "
                        "This choice only affects this browser session."
                    ),
                    key="gemini_primary_picker",
                )

                if selected_name != names[0]:
                    st.session_state.gemini_primary_name = selected_name
                    st.rerun()
        else:
            st.warning(
                "AI is not configured on the server yet. "
                "Once it is configured, you will not need to paste an API key into ToonScripture."
            )




# =========================================================
# HEADER
# =========================================================

st.title("ToonScripture OS")
st.caption(
    "A simple workspace for turning a Bible story into a cinematic YouTube episode."
)

MAIN_SECTIONS = [
    "🏠 Home",
    "📋 Story Checklist",
    "✍️ Story & Script",
    "🎨 Visual Bible",
    "🎞️ Scene Production",
    "🎙️ Audio",
    "📺 YouTube",
    "📦 Export",
]

if "main_section" not in st.session_state:
    st.session_state.main_section = "🏠 Home"

main_section = st.segmented_control(
    "Workspace section",
    MAIN_SECTIONS,
    key="main_section",
    label_visibility="collapsed",
)


# =========================================================
# HOME
# =========================================================

if main_section == "🏠 Home":
    st.header("What would you like to do?")

    st.markdown("### How it works")
    h1, h2, h3, h4, h5 = st.columns(5)
    h1.markdown("**1. Pick a story**\n\nChoose what you want to make.")
    h2.markdown("**2. Write it**\n\nShape the story and narration.")
    h3.markdown("**3. Lock the look**\n\nApprove characters and locations.")
    h4.markdown("**4. Make scenes**\n\nGenerate and check each shot.")
    h5.markdown("**5. Publish**\n\nCreate audio and YouTube packaging.")

    st.divider()

    if project:
        st.markdown("## Continue your current episode")
        render_project_card(project)
        st.caption(
            "Open any tab above whenever you want. "
            "The app shows the recommended next step, but it never locks you into it."
        )
        st.divider()

    summary = catalog_summary()

    if summary["people_total"] == 0:
        st.markdown("## Add your story catalogue")
        st.write(
            "Upload your ToonScripture planning spreadsheet once. "
            "After that, the stories will live in the database and you will not need the spreadsheet for daily use."
        )

        upload = st.file_uploader(
            "Choose the planning spreadsheet",
            type=["xlsx"],
            key="catalog_upload",
        )

        if upload and st.button(
            "Import my story catalogue",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Adding your stories to ToonScripture..."):
                result = import_spreadsheet(upload.getvalue())

            st.success(
                f"Done. {result['people_total']} story/character entries "
                f"and {result['series_total']} series were added."
            )
            st.rerun()

    else:
        st.markdown("## Start a new episode")
        st.write(
            "Search for the Bible person or story you want to work on. "
            "Then give the episode a specific title."
        )

        selected_series_filter = st.session_state.get("selected_series_filter", "")

        if selected_series_filter:
            st.info(f"Showing stories from: {selected_series_filter}")
            if st.button(
                "Show all stories",
                key="clear_series_filter",
            ):
                st.session_state.pop("selected_series_filter", None)
                st.rerun()

        search = st.text_input(
            "Search the catalogue",
            placeholder="Example: Daniel, Esther, Moses, Ruth...",
        )

        rows = list_catalog_people(
            search=search,
            playlist=selected_series_filter or "",
            limit=1000,
        )

        rows = [
            row for row in rows
            if (row.get("production_status") or "not_started") != "completed"
        ]

        if rows:
            choices = {
                row["id"]: (
                    f"{row['name']} · "
                    f"{row.get('bible_references') or 'Bible reference not set'}"
                )
                for row in rows
            }

            selected_id = st.selectbox(
                "Choose a story or character",
                list(choices.keys()),
                format_func=lambda cid: choices[cid],
            )

            selected = next(row for row in rows if row["id"] == selected_id)

            st.markdown(f"### {selected['name']}")

            if selected.get("story_role"):
                st.write(selected["story_role"])

            info1, info2, info3 = st.columns(3)

            with info1:
                st.markdown("**Bible**")
                st.write(selected.get("bible_references") or "Not set")

            with info2:
                st.markdown("**Priority**")
                st.write(selected.get("priority") or "Not set")

            with info3:
                st.markdown("**Series**")
                st.write(selected.get("playlist_series") or "Not assigned")

            if selected.get("primary_environment"):
                st.markdown(
                    f"**Main setting:** {selected['primary_environment']}"
                )

            if selected.get("youtube_hook"):
                st.info(selected["youtube_hook"])

            st.markdown("### Name this episode")

            episode_title = st.text_input(
                "Episode title",
                value=selected["name"],
                help="Make it specific, e.g. Daniel in the Lions' Den.",
            )

            bible_reference = st.text_input(
                "Bible reference",
                value=selected.get("bible_references") or "",
            )

            runtime = st.select_slider(
                "How long should the episode be?",
                options=[4.0, 6.0, 8.0, 10.0, 12.0, 15.0],
                value=8.0,
                format_func=lambda x: f"{int(x)} minutes",
            )

            if st.button(
                "Create this episode",
                type="primary",
                use_container_width=True,
            ):
                pid = create_project(
                    episode_title,
                    bible_reference,
                    runtime,
                    "long_form",
                )
                link_project(
                    pid,
                    person_id=selected_id,
                    episode_title=episode_title,
                )
                set_catalog_production_status(
                    selected_id,
                    "in_progress",
                )
                st.session_state.project_id = pid
                st.success("Episode created.")
                st.rerun()
        else:
            st.warning("No matching story was found.")

        with st.expander("Browse series ideas"):
            st.caption(
                "Choose a series to filter the story list above."
            )

            for item in list_series():
                st.markdown(f"**{item['series_name']}**")

                if item.get("core_concept"):
                    st.write(item["core_concept"])

                if item.get("best_starter_episodes"):
                    st.caption(
                        "Good starting episodes: "
                        + str(item["best_starter_episodes"])
                    )

                if st.button(
                    f"Explore {item['series_name']}",
                    key=f"series_{item['id']}",
                    use_container_width=True,
                ):
                    st.session_state.selected_series_filter = item["series_name"]
                    st.rerun()

                st.divider()

    with st.expander("Create an episode without the catalogue"):
        manual_title = st.text_input(
            "Story title",
            key="manual_title",
            placeholder="Example: Daniel in the Lions' Den",
        )
        manual_reference = st.text_input(
            "Bible reference",
            key="manual_reference",
            placeholder="Example: Daniel 6",
        )
        manual_runtime = st.select_slider(
            "Target length",
            options=[4.0, 6.0, 8.0, 10.0, 12.0, 15.0],
            value=8.0,
            format_func=lambda x: f"{int(x)} minutes",
            key="manual_runtime",
        )

        if st.button(
            "Create manual episode",
            use_container_width=True,
        ):
            if not manual_title.strip():
                st.error("Enter a story title first.")
            else:
                pid = create_project(
                    manual_title,
                    manual_reference,
                    manual_runtime,
                    "long_form",
                )
                st.session_state.project_id = pid
                st.rerun()


project = (
    get_project(st.session_state.get("project_id"))
    if st.session_state.get("project_id")
    else None
)


# =========================================================
# STORY CHECKLIST
# =========================================================

if main_section == "📋 Story Checklist":
    st.header("Story Checklist")
    st.write(
        "This is your master production list. Every story in your ToonScripture catalogue "
        "lives here, so you can see what is finished, what is in progress, and what is still waiting."
    )

    progress = catalog_progress_summary()

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("All stories", progress["total"])
    p2.metric("Finished", progress["completed"])
    p3.metric("In progress", progress["in_progress"])
    p4.metric("Not started", progress["not_started"])

    if progress["total"]:
        st.progress(
            progress["completed"] / progress["total"],
            text=f"{progress['completed']} of {progress['total']} completed",
        )

    st.divider()

    f1, f2, f3 = st.columns([2, 1, 1])

    with f1:
        checklist_search = st.text_input(
            "Search stories",
            placeholder="Daniel, Esther, Moses...",
            key="checklist_search",
        )

    with f2:
        checklist_status = st.selectbox(
            "Status",
            ["All", "Finished", "In progress", "Not started"],
            key="checklist_status",
        )

    with f3:
        checklist_priority = st.selectbox(
            "Priority",
            ["All", "High", "Medium", "Low"],
            key="checklist_priority",
        )

    checklist_rows = list_catalog_people(
        search=checklist_search,
        priority="" if checklist_priority == "All" else checklist_priority,
        limit=1000,
    )

    status_map = {
        "Finished": "completed",
        "In progress": "in_progress",
        "Not started": "not_started",
    }

    if checklist_status != "All":
        wanted = status_map[checklist_status]
        checklist_rows = [
            row for row in checklist_rows
            if (row.get("production_status") or "not_started") == wanted
        ]

    st.caption(f"{len(checklist_rows)} stories shown")

    for row in checklist_rows:
        current_status = row.get("production_status") or "not_started"
        is_done = current_status == "completed"

        left, right = st.columns([6, 2])

        with left:
            changed_done = st.checkbox(
                f"{row['name']} · {row.get('bible_references') or 'Reference not set'}",
                value=is_done,
                key=f"done_{row['id']}",
            )

            if row.get("story_role"):
                st.caption(row["story_role"])

        with right:
            if changed_done != is_done:
                set_catalog_production_status(
                    row["id"],
                    "completed" if changed_done else "not_started",
                )
                st.rerun()

            if current_status == "completed":
                st.success("Finished")
            elif current_status == "in_progress":
                st.warning("In progress")
            else:
                st.caption("Not started")

        st.divider()


# =========================================================
# STORY & SCRIPT
# =========================================================

if main_section == "✍️ Story & Script":
    if not project:
        st.info("Create or choose an episode from Home first.")
    else:
        st.header(project["story_name"])
        st.caption(
            "This section turns the Bible story into a strong YouTube narration."
        )

        treatment = load_json(project, "treatment_json", {})
        script = load_json(project, "script_json", {})
        critique = load_json(project, "critique_json", {})

        story_steps = [
            "1. Shape the story",
            "2. Write the script",
            "3. Check viewer retention",
        ]

        if "story_step" not in st.session_state:
            if critique:
                st.session_state.story_step = story_steps[2]
            elif script:
                st.session_state.story_step = story_steps[1]
            else:
                st.session_state.story_step = story_steps[0]

        step = st.radio(
            "Choose what you want to work on",
            story_steps,
            horizontal=True,
            key="story_step",
        )

        if step == "1. Shape the story":
            st.subheader("Shape the story")
            st.write(
                "ToonScripture will map the key events, emotional arc, "
                "historical context and the strongest opening."
            )

            if st.button(
                "Create story treatment"
                if not treatment
                else "Create a new treatment",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner("Shaping the story..."):
                        develop_treatment(project["id"])
                    st.rerun()
                except Exception as exc:
                    st.error(
                        "The AI could not create the treatment yet. "
                        "I have kept your episode saved, so nothing was lost."
                    )
                    with st.expander("Technical details"):
                        st.code(str(exc))

            if treatment:
                if treatment.get("opening_hook"):
                    st.markdown("### Opening idea")
                    st.write(treatment["opening_hook"])

                if treatment.get("emotional_arc"):
                    st.markdown("### Emotional journey")
                    st.write(treatment["emotional_arc"])

                if treatment.get("story_beats"):
                    st.markdown("### Main story moments")
                    for beat in treatment["story_beats"]:
                        st.write("•", beat)

                with st.expander("See full treatment"):
                    if treatment.get("core_story"):
                        st.markdown("### Core story")
                        st.write(treatment["core_story"])

                    if treatment.get("scriptural_anchor"):
                        st.markdown("### Scriptural anchors")
                        for item in treatment["scriptural_anchor"]:
                            st.write("•", item)

                    if treatment.get("historical_context"):
                        st.markdown("### Historical context")
                        for item in treatment["historical_context"]:
                            st.write("•", item)

                    if treatment.get("cinematic_interpretations"):
                        st.markdown("### Cinematic interpretation")
                        for item in treatment["cinematic_interpretations"]:
                            st.write("•", item)

                    if treatment.get("accuracy_risks"):
                        st.markdown("### Accuracy notes")
                        for item in treatment["accuracy_risks"]:
                            st.write("•", item)

                    if treatment.get("ending_payoff"):
                        st.markdown("### Ending payoff")
                        st.write(treatment["ending_payoff"])

                st.divider()
                st.button(
                    "Next → Write the script",
                    type="primary",
                    use_container_width=True,
                    key="next_to_script",
                    on_click=go_to_story_step,
                    args=("2. Write the script",),
                )

        elif step == "2. Write the script":
            if not treatment:
                st.info(
                    "Create the story treatment first so the script has a clear direction."
                )
            else:
                st.subheader("Write the narration script")
                st.write(
                    "The script is written for cinematic narration and viewer retention."
                )

                script_error = None

                if st.button(
                    "Write the script"
                    if not script
                    else "Rewrite the script",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        with st.spinner("Writing the episode..."):
                            draft_script(project["id"])
                        st.rerun()
                    except Exception as exc:
                        script_error = str(exc)

                if script_error:
                    if "quota" in script_error.lower() or "429" in script_error:
                        st.warning(
                            "The primary Gemini project has reached its current API limit. "
                            "Your existing script is still saved and has not been replaced. "
                            "You can keep working with it and retry the rewrite later."
                        )
                    else:
                        st.error(
                            "The script could not be generated right now. "
                            "Your existing work is still saved."
                        )

                    with st.expander("Technical details"):
                        st.code(script_error)

                show_script(script)

                if script:
                    st.divider()
                    st.button(
                        "Next → Check viewer retention",
                        type="primary",
                        use_container_width=True,
                        key="next_to_retention",
                        on_click=go_to_story_step,
                        args=("3. Check viewer retention",),
                    )

        else:
            if not script:
                st.info("Write the script first.")
            else:
                st.subheader("Check viewer retention")
                st.write(
                    "This checks the hook, pacing, repetition, emotional build and payoff."
                )

                review_error = None

                if st.button(
                    "Review the script"
                    if not critique
                    else "Review the script again",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        with st.spinner("Reviewing the script..."):
                            critique_script(project["id"])
                        st.rerun()
                    except Exception as exc:
                        review_error = str(exc)

                if review_error:
                    if "quota" in review_error.lower() or "429" in review_error:
                        st.warning(
                            "The AI review limit has been reached for the connected Gemini API project. "
                            "Your script is safe and nothing has been lost. You can retry the retention "
                            "review later, or continue to the Visual Bible now."
                        )
                    else:
                        st.error(
                            "The retention review could not be completed right now. "
                            "Your script is saved, so you can retry later."
                        )

                    with st.expander("Technical details"):
                        st.code(review_error)

                    st.button(
                        "Continue for now → Visual Bible",
                        type="primary",
                        use_container_width=True,
                        key="skip_retention_to_visual_bible",
                        on_click=go_to_main_section,
                        args=("🎨 Visual Bible",),
                    )

                if critique:
                    score = critique.get("score_100")
                    if score is not None:
                        st.metric("Retention score", f"{score}/100")

                    left, right = st.columns(2)

                    with left:
                        st.markdown("### What works")
                        for item in critique.get("strengths", []):
                            st.write("•", item)

                    with right:
                        st.markdown("### What needs attention")
                        for item in critique.get("problems", []):
                            st.write("•", item)

                    with st.expander("Recommended changes"):
                        st.markdown("**Add**")
                        for item in critique.get("recommended_additions", []):
                            st.write("•", item)

                        st.markdown("**Cut or tighten**")
                        for item in critique.get("recommended_cuts", []):
                            st.write("•", item)

                    st.divider()
                    st.success("Story and script preparation is complete.")
                    st.caption(
                        "Next, lock the appearance of characters, locations, groups and props."
                    )
                    st.button(
                        "Next → Visual Bible",
                        type="primary",
                        use_container_width=True,
                        key="next_to_visual_bible",
                        on_click=go_to_main_section,
                        args=("🎨 Visual Bible",),
                    )


# =========================================================
# VISUAL BIBLE
# =========================================================

if main_section == "🎨 Visual Bible":
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("script_json"):
        st.info(
            "Finish the script first. The Visual Bible is built from the approved story."
        )
    else:
        st.header("Visual Bible")
        st.write(
            "This keeps the same people, uniforms, creatures, locations and props "
            "looking consistent from scene to scene."
        )

        bible = load_json(project, "character_bible_json", {})

        if not bible:
            st.info(
                "You have not created the Visual Bible for this episode yet."
            )

        visual_bible_error = None

        if st.button(
            "Build the Visual Bible"
            if not bible
            else "Rebuild the Visual Bible",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner(
                    "Building people, groups, locations and props..."
                ):
                    build_character_bible(project["id"])
                st.rerun()
            except Exception as exc:
                visual_bible_error = str(exc)

        if visual_bible_error:
            if "quota" in visual_bible_error.lower() or "429" in visual_bible_error:
                st.warning(
                    "The selected Gemini project has reached its current API limit. "
                    "Nothing was lost. Open Settings, choose another configured AI project, "
                    "then click Build the Visual Bible again."
                )
            else:
                st.error(
                    "The Visual Bible could not be created right now. "
                    "Your episode and script are still saved."
                )

            with st.expander("Technical details"):
                st.code(visual_bible_error)

        if bible:
            categories = {
                "Main characters": (
                    "characters",
                    "master_character_prompt",
                    "identity_lock",
                ),
                "Supporting characters": (
                    "supporting_characters",
                    "master_character_prompt",
                    "identity_lock",
                ),
                "Groups & uniforms": (
                    "character_groups",
                    "master_group_prompt",
                    "group_identity_lock",
                ),
                "Locations": (
                    "locations",
                    "master_environment_prompt",
                    "environment_lock",
                ),
                "Props": (
                    "props",
                    "master_prop_prompt",
                    None,
                ),
            }

            category = st.selectbox(
                "What do you want to review?",
                list(categories.keys()),
            )

            key, prompt_key, lock_key = categories[category]
            items = bible.get(key, [])

            if not items:
                st.caption("No entries were created in this category.")
            else:
                names = [
                    item.get("name") or f"Item {i + 1}"
                    for i, item in enumerate(items)
                ]

                selected_name = st.selectbox(
                    category,
                    names,
                    key=f"{project['id']}_{key}_selector",
                )

                item = items[names.index(selected_name)]

                st.markdown(f"## {selected_name}")

                role = (
                    item.get("role")
                    or item.get("story_function")
                    or item.get("story_purpose")
                )

                if role:
                    st.caption(role)

                prompt = item.get(prompt_key)
                if prompt:
                    st.markdown("### Reference image prompt")
                    st.caption(
                        "Copy this into Google Flow to create the approved reference image."
                    )
                    st.code(prompt, wrap_lines=True)

                if lock_key and item.get(lock_key):
                    st.markdown("### Continuity lock")
                    st.caption(
                        "This description is reused in scenes so the design does not drift."
                    )
                    st.code(item[lock_key], wrap_lines=True)

                if key == "character_groups":
                    variation = item.get("allowed_individual_variation", [])
                    if variation:
                        st.markdown("### What may vary between members")
                        for value in variation:
                            st.write("•", value)

                st.divider()
                st.markdown("### Approved reference image")
                st.caption(
                    "Generate the image in Google Flow, then upload the version you want "
                    "ToonScripture to treat as the official visual reference."
                )

                saved_reference = get_reference_asset(
                    project["id"],
                    key,
                    selected_name,
                )

                if saved_reference and saved_reference.get("signed_url"):
                    st.image(
                        saved_reference["signed_url"],
                        caption="Approved reference",
                        width=360,
                    )
                    st.success("This reference is locked for continuity.")

                uploaded_reference = st.file_uploader(
                    "Upload approved reference image",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"reference_upload_{project['id']}_{key}_{selected_name}",
                )

                if uploaded_reference and st.button(
                    "Use this as the official reference",
                    type="primary",
                    use_container_width=True,
                    key=f"save_reference_{project['id']}_{key}_{selected_name}",
                ):
                    with st.spinner("Saving the approved reference..."):
                        save_reference_asset(
                            project_id=project["id"],
                            reference_type=key,
                            name=selected_name,
                            file_bytes=uploaded_reference.getvalue(),
                            filename=uploaded_reference.name,
                            content_type=uploaded_reference.type or "application/octet-stream",
                            master_prompt=prompt,
                            identity_lock=item.get(lock_key) if lock_key else None,
                            negative_lock=(
                                item.get("negative_identity_lock")
                                or item.get("negative_group_lock")
                            ),
                        )
                    st.success("Reference saved.")
                    st.rerun()

                with st.expander("See all visual details"):
                    st.json(item)

        if bible:
            st.divider()
            st.button(
                "Next → Scene Production",
                type="primary",
                use_container_width=True,
                key="next_to_scene_production",
                on_click=go_to_main_section,
                args=("🎞️ Scene Production",),
            )


# =========================================================
# SCENE PRODUCTION
# =========================================================

if main_section == "🎞️ Scene Production":
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("character_bible_json"):
        st.info(
            "Build the Visual Bible first so the scene prompts can keep continuity."
        )
    else:
        st.header("Scene Production")
        st.write(
            "Each scene explains exactly what the shot starts with, "
            "what happens, and how it must end."
        )

        scene_data = load_json(project, "scenes_json", {})
        scenes = scene_data.get("scenes", [])

        if st.button(
            "Build scene prompts"
            if not scenes
            else "Rebuild scene prompts",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Breaking the story into production scenes..."):
                plan_scenes(project["id"])
            st.rerun()

        if scenes:
            labels = [
                f"Scene {scene.get('scene_number', i + 1)} · "
                f"{scene.get('scene_title') or 'Untitled'}"
                for i, scene in enumerate(scenes)
            ]

            selected_label = st.selectbox(
                "Choose a scene",
                labels,
            )

            scene = scenes[labels.index(selected_label)]

            st.markdown(f"## {selected_label}")

            if scene.get("narration"):
                st.markdown("### Narration")
                st.write(scene["narration"])

            c1, c2, c3 = st.columns(3)

            with c1:
                st.markdown("### 1. Start")
                st.write(scene.get("start_state") or "—")

            with c2:
                st.markdown("### 2. Action")
                st.write(scene.get("dominant_action") or "—")

            with c3:
                st.markdown("### 3. End")
                st.write(scene.get("end_state") or "—")

            scene_package = compose_scene_package(project["id"], scene)
            scene_refs = reference_summary(scene_package)

            if scene_refs:
                st.markdown("### Continuity references")
                approved_count = sum(1 for ref in scene_refs if ref["approved"])
                st.caption(
                    f"{approved_count} of {len(scene_refs)} relevant visual references are approved."
                )
                for ref in scene_refs:
                    icon = "✅" if ref["approved"] else "○"
                    st.write(
                        f"{icon} {ref['name']} · "
                        f"{'reference locked' if ref['approved'] else 'reference not uploaded yet'}"
                    )

            st.markdown("### Frame prompt")
            st.caption(
                "Use this complete prompt to generate the still image. "
                "It automatically includes the continuity locks for this scene."
            )
            st.code(scene_package.get("frame_prompt") or "", wrap_lines=True)

            st.markdown("### Video prompt")
            st.caption(
                "Use this after the still frame is approved. "
                "It preserves the start → action → end movement logic."
            )
            st.code(scene_package.get("video_prompt") or "", wrap_lines=True)

            with st.expander("Physical rules and things that must not happen"):
                constraints = scene.get("physical_constraints", [])
                negatives = scene.get("negative_constraints", [])

                if constraints:
                    st.markdown("**Physical / spatial rules**")
                    for item in constraints:
                        st.write("•", item)

                if negatives:
                    st.markdown("**Do not allow**")
                    for item in negatives:
                        st.write("•", item)

            st.divider()
            st.markdown("### Check the generated frame")
            st.write(
                "After you generate the still image in Flow, upload it here. "
                "ToonScripture will compare it with the scene and Visual Bible before you animate it."
            )

            frame_upload = st.file_uploader(
                "Upload generated frame",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"scene_frame_{project['id']}_{selected_label}",
            )

            if frame_upload and st.button(
                "Check this frame",
                type="primary",
                use_container_width=True,
                key=f"review_frame_{project['id']}_{selected_label}",
            ):
                if not _api_key():
                    st.error("Connect AI from the sidebar first.")
                else:
                    with st.spinner("Checking identity, scene accuracy and physical logic..."):
                        review = review_scene_frame(
                            project["id"],
                            scene,
                            frame_upload.getvalue(),
                            frame_upload.type or "image/png",
                        )

                        save_project_asset(
                            project_id=project["id"],
                            asset_type="scene_frame",
                            name=selected_label,
                            file_bytes=frame_upload.getvalue(),
                            filename=frame_upload.name,
                            content_type=frame_upload.type or "image/png",
                            metadata={
                                "scene_number": scene.get("scene_number"),
                                "scene_title": scene.get("scene_title"),
                                "continuity_review": review,
                            },
                        )

                    st.session_state[
                        f"review_result_{project['id']}_{selected_label}"
                    ] = review

            review = st.session_state.get(
                f"review_result_{project['id']}_{selected_label}"
            )

            if review:
                verdict = review.get("verdict", "")
                score = review.get("overall_score")

                if verdict == "approved":
                    st.success(
                        f"Approved for animation"
                        + (f" · {score}/100" if score is not None else "")
                    )
                elif verdict == "minor_fix":
                    st.warning(
                        f"Almost there — make a small fix"
                        + (f" · {score}/100" if score is not None else "")
                    )
                else:
                    st.error(
                        f"Regenerate this frame"
                        + (f" · {score}/100" if score is not None else "")
                    )

                for problem in review.get("problems", []):
                    st.write("•", problem)

                if review.get("regeneration_instruction"):
                    st.markdown("**What to change**")
                    st.code(
                        review["regeneration_instruction"],
                        wrap_lines=True,
                    )

        if scenes:
            st.divider()
            st.button(
                "Next → Audio",
                type="primary",
                use_container_width=True,
                key="next_to_audio",
                on_click=go_to_main_section,
                args=("🎙️ Audio",),
            )


# =========================================================
# AUDIO
# =========================================================

if main_section == "🎙️ Audio":
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("script_json"):
        st.info("Finish the script first.")
    else:
        st.header("Narration Audio")
        st.write(
            "Turn the finished script into a voiceover you can take straight into your edit."
        )

        full_narration = narration_text(project["id"])

        if not full_narration:
            st.info("The script does not contain narration yet.")
        else:
            st.metric(
                "Narration length",
                f"{len(full_narration.split()):,} words",
            )

            with st.expander("Preview narration text"):
                st.write(full_narration)

            voices = list_tts_voices()
            voice_names = []
            voice_lookup = {}

            for voice in voices:
                voice_id = (
                    voice.get("id")
                    or voice.get("name")
                    or voice.get("voice_id")
                    or "Algenib"
                )
                display = (
                    voice.get("display_name")
                    or voice.get("displayName")
                    or voice_id
                )
                voice_names.append(display)
                voice_lookup[display] = voice_id

            preferred_index = (
                voice_names.index("Algenib")
                if "Algenib" in voice_names
                else 0
            )

            selected_voice = st.selectbox(
                "Narrator voice",
                voice_names,
                index=preferred_index,
                help="Algenib is the recommended starting voice for ToonScripture.",
            )

            voice_direction = st.text_area(
                "Voice direction",
                value=(
                    "Warm cinematic storyteller for a family audience. "
                    "Calm authority, clear diction, emotionally dynamic through suspense, "
                    "reflection, wonder and victory. Never robotic, frightening, preachy "
                    "or like a movie-trailer announcer."
                ),
                height=120,
            )

            if st.button(
                "Create narration audio",
                type="primary",
                use_container_width=True,
            ):
                if not _api_key():
                    st.error("Connect AI from the sidebar first.")
                else:
                    with st.spinner("Creating narration audio..."):
                        audio_bytes = generate_tts_bytes(
                            full_narration,
                            voice_id=voice_lookup[selected_voice],
                            style_instruction=voice_direction,
                        )

                        saved_audio = save_project_asset(
                            project_id=project["id"],
                            asset_type="narration_audio",
                            name="Narration",
                            file_bytes=audio_bytes,
                            filename=f"{project['id']}_narration.wav",
                            content_type="audio/wav",
                            metadata={
                                "voice": voice_lookup[selected_voice],
                                "voice_direction": voice_direction,
                            },
                        )

                    st.session_state[
                        f"latest_audio_{project['id']}"
                    ] = audio_bytes
                    st.success("Narration audio created and saved.")

            latest_audio = st.session_state.get(
                f"latest_audio_{project['id']}"
            )

            if latest_audio:
                st.audio(latest_audio, format="audio/wav")
                st.download_button(
                    "Download narration audio",
                    data=latest_audio,
                    file_name=f"{project['story_name']}_narration.wav",
                    mime="audio/wav",
                    use_container_width=True,
                )

            saved_audio_files = list_project_assets(
                project["id"],
                "narration_audio",
            )

            if saved_audio_files:
                latest = saved_audio_files[0]
                url = signed_asset_url(latest.get("storage_path"))
                if url and not latest_audio:
                    st.markdown("### Latest saved narration")
                    st.audio(url)

            if saved_audio_files or latest_audio:
                st.divider()
                st.button(
                    "Next → YouTube",
                    type="primary",
                    use_container_width=True,
                    key="next_to_youtube",
                    on_click=go_to_main_section,
                    args=("📺 YouTube",),
                )


# =========================================================
# YOUTUBE
# =========================================================

if main_section == "📺 YouTube":
    if not project:
        st.info("Choose an episode first.")
    elif not project.get("script_json"):
        st.info("Finish the script first.")
    else:
        st.header("YouTube Package")
        st.write(
            "Create the title, thumbnail direction, description and pinned comment."
        )

        package = load_json(project, "package_json", {})

        if st.button(
            "Create YouTube package"
            if not package
            else "Create a new YouTube package",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Packaging the episode..."):
                make_package(project["id"])
            st.rerun()

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
                        if isinstance(option, dict):
                            st.write("•", option.get("title") or str(option))
                        else:
                            st.write("•", option)

            thumbnail = package.get("strongest_thumbnail_recommendation")
            if thumbnail:
                st.markdown("### Thumbnail direction")
                if isinstance(thumbnail, dict):
                    for key, value in thumbnail.items():
                        st.markdown(f"**{key.replace('_', ' ').title()}**")
                        st.write(value)
                else:
                    st.write(thumbnail)

            description = package.get("youtube_description")
            if description:
                st.markdown("### Description")
                st.code(description, wrap_lines=True)

            pinned = package.get("pinned_comment")
            if pinned:
                st.markdown("### Pinned comment")
                st.code(pinned, wrap_lines=True)

        st.divider()
        st.markdown("## After you publish")
        st.write(
            "Come back with the YouTube numbers. ToonScripture will keep a history "
            "so each new episode can learn from what actually worked."
        )

        with st.expander("Record performance"):
            m1, m2 = st.columns(2)
            with m1:
                views = st.number_input(
                    "Views",
                    min_value=0,
                    value=0,
                    step=100,
                    key=f"views_{project['id']}",
                )
                impressions = st.number_input(
                    "Impressions",
                    min_value=0,
                    value=0,
                    step=100,
                    key=f"impressions_{project['id']}",
                )
                ctr = st.number_input(
                    "Click-through rate (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    step=0.1,
                    key=f"ctr_{project['id']}",
                )
            with m2:
                avd = st.number_input(
                    "Average view duration (seconds)",
                    min_value=0,
                    value=0,
                    step=10,
                    key=f"avd_{project['id']}",
                )
                apv = st.number_input(
                    "Average percentage viewed (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    step=0.1,
                    key=f"apv_{project['id']}",
                )
                subs = st.number_input(
                    "Subscribers gained",
                    min_value=0,
                    value=0,
                    step=1,
                    key=f"subs_{project['id']}",
                )

            metric_notes = st.text_area(
                "What did you notice?",
                placeholder="Example: viewers dropped during the palace explanation, thumbnail performed well...",
                key=f"metric_notes_{project['id']}",
            )

            if st.button(
                "Save performance",
                use_container_width=True,
                key=f"save_metrics_{project['id']}",
            ):
                save_episode_metrics(
                    project_id=project["id"],
                    views=int(views),
                    impressions=int(impressions),
                    ctr=float(ctr),
                    average_view_duration_seconds=int(avd),
                    average_percentage_viewed=float(apv),
                    subscribers_gained=int(subs),
                    notes=metric_notes,
                )
                st.success("Performance saved.")

        history = list_episode_metrics(project["id"])
        if history:
            latest_metrics = history[0]
            st.caption("Latest saved performance")
            h1, h2, h3 = st.columns(3)
            h1.metric("Views", f"{latest_metrics.get('views') or 0:,}")
            h2.metric("CTR", f"{latest_metrics.get('ctr') or 0:.1f}%")
            h3.metric(
                "Avg. viewed",
                f"{latest_metrics.get('average_percentage_viewed') or 0:.1f}%",
            )

        if package:
            st.divider()
            st.button(
                "Next → Export",
                type="primary",
                use_container_width=True,
                key="next_to_export",
                on_click=go_to_main_section,
                args=("📦 Export",),
            )


# =========================================================
# EXPORT
# =========================================================

if main_section == "📦 Export":
    if not project:
        st.info("Choose an episode first.")
    else:
        st.header("Export Project")
        st.write(
            "Take a clean copy of the episode with you for CapCut, archiving or backup."
        )

        bundle = {
            "project": {
                "id": project.get("id"),
                "story_name": project.get("story_name"),
                "bible_reference": project.get("bible_reference"),
                "target_minutes": project.get("target_minutes"),
                "format": project.get("format"),
                "status": project.get("status"),
            },
            "treatment": load_json(project, "treatment_json", {}),
            "script": load_json(project, "script_json", {}),
            "retention_review": load_json(project, "critique_json", {}),
            "visual_bible": load_json(project, "character_bible_json", {}),
            "scenes": load_json(project, "scenes_json", {}),
            "youtube_package": load_json(project, "package_json", {}),
        }

        json_bytes = json.dumps(
            bundle,
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")

        st.download_button(
            "Download full project backup",
            data=json_bytes,
            file_name=f"{project['story_name']}_toonscripture.json",
            mime="application/json",
            type="primary",
            use_container_width=True,
        )

        scene_data = bundle["scenes"]
        scene_list = scene_data.get("scenes", []) if isinstance(scene_data, dict) else []

        lines = [
            f"TOONSCRIPTURE PRODUCTION PACK",
            f"Story: {project['story_name']}",
            f"Bible: {project.get('bible_reference') or ''}",
            f"Target runtime: {project.get('target_minutes')} minutes",
            "",
        ]

        script = bundle["script"]
        if script:
            lines += ["NARRATION SCRIPT", "=" * 60, narration_text(project["id"]), ""]

        if scene_list:
            lines += ["SCENE PROMPTS", "=" * 60]
            for scene in scene_list:
                package = compose_scene_package(project["id"], scene)
                lines += [
                    f"SCENE {scene.get('scene_number', '')}: {scene.get('scene_title', '')}",
                    "",
                    "NARRATION:",
                    str(scene.get("narration") or ""),
                    "",
                    "FRAME PROMPT:",
                    package.get("frame_prompt") or "",
                    "",
                    "VIDEO PROMPT:",
                    package.get("video_prompt") or "",
                    "",
                    "-" * 60,
                    "",
                ]

        production_text = "\n".join(lines).encode("utf-8")

        st.download_button(
            "Download production text for editing",
            data=production_text,
            file_name=f"{project['story_name']}_production_pack.txt",
            mime="text/plain",
            use_container_width=True,
        )

        st.caption(
            "Your working data is also saved in the cloud database. "
            "These downloads are portable copies for your own archive."
        )

