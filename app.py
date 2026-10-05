import streamlit as st

from db import (
    init_db,
    list_projects,
    get_project,
    create_project,
    load_json,
    catalog_summary,
    list_catalog_people,
    list_series,
    link_project,
    import_spreadsheet,
    seed_catalog_if_empty,
    save_reference_asset,
    get_reference_asset,
    using_supabase,
    auth_sign_in,
    auth_restore,
    auth_sign_out,
)
from workflow import (
    develop_treatment,
    draft_script,
    critique_script,
    build_character_bible,
    plan_scenes,
    make_package,
)

st.set_page_config(
    page_title="ToonScripture OS",
    page_icon="🎬",
    layout="wide",
)

init_db()


# =========================================================
# SIGN IN
# =========================================================

if using_supabase():
    if st.session_state.get("auth_access_token") and st.session_state.get("auth_refresh_token"):
        try:
            restored = auth_restore(
                st.session_state.auth_access_token,
                st.session_state.auth_refresh_token,
            )
            st.session_state.auth_access_token = restored["access_token"]
            st.session_state.auth_refresh_token = restored["refresh_token"]
            st.session_state.auth_email = restored.get("email")
        except Exception:
            for key in [
                "auth_access_token",
                "auth_refresh_token",
                "auth_email",
            ]:
                st.session_state.pop(key, None)

    if not st.session_state.get("auth_access_token"):
        st.title("🎬 ToonScripture")
        st.subheader("Welcome back")
        st.write(
            "Sign in to open your Bible-story production workspace. "
            "Your projects, scripts and production progress are saved securely online."
        )

        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button(
                "Sign in to ToonScripture",
                type="primary",
                use_container_width=True,
            )

        if submit:
            try:
                session = auth_sign_in(email, password)
                st.session_state.auth_access_token = session["access_token"]
                st.session_state.auth_refresh_token = session["refresh_token"]
                st.session_state.auth_email = session.get("email")
                st.rerun()
            except Exception as exc:
                st.error("We couldn't sign you in. Check your email and password and try again.")

        st.stop()

    # First successful cloud sign-in automatically restores the planning catalogue.
    try:
        seed_catalog_if_empty()
    except Exception as exc:
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
        st.markdown("### Opening hook")
        st.write(script["hook"])

    sections = script.get("sections", [])
    if sections:
        labels = [
            section.get("name") or f"Section {i + 1}"
            for i, section in enumerate(sections)
        ]
        selected = st.selectbox(
            "Choose a script section",
            labels,
            key="script_section_selector",
        )
        section = sections[labels.index(selected)]

        st.markdown(f"### {selected}")

        if section.get("purpose"):
            st.caption(section["purpose"])

        if section.get("narration"):
            st.write(section["narration"])

        dialogue = section.get("dialogue")
        if dialogue:
            st.markdown("**Dialogue**")
            for line in dialogue if isinstance(dialogue, list) else [dialogue]:
                st.write(line)


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

    chosen = st.selectbox(
        "Episode",
        ids,
        index=index,
        format_func=lambda pid: labels[pid],
        label_visibility="collapsed",
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

    if project:
        done, total = project_progress(project)
        st.markdown(f"**{project['story_name']}**")
        st.caption(
            f"{project.get('bible_reference') or 'No reference'} · "
            f"{project.get('target_minutes', 0)} min"
        )
        st.progress(done / total)
        st.caption(f"{done}/{total} stages complete")
    else:
        st.caption("No episode selected.")

    st.divider()
    st.caption("You can move between sections at any time.")

    if using_supabase():
        if st.session_state.get("auth_email"):
            st.caption(f"Signed in as {st.session_state.auth_email}")
        if st.button("Sign out", use_container_width=True):
            auth_sign_out(
                st.session_state.get("auth_access_token"),
                st.session_state.get("auth_refresh_token"),
            )
            for key in [
                "auth_access_token",
                "auth_refresh_token",
                "auth_email",
                "project_id",
            ]:
                st.session_state.pop(key, None)
            st.rerun()


# =========================================================
# HEADER
# =========================================================

st.title("ToonScripture OS")
st.caption(
    "A simple workspace for turning a Bible story into a cinematic YouTube episode."
)

nav = st.tabs(
    [
        "🏠 Home",
        "✍️ Story & Script",
        "🎨 Visual Bible",
        "🎞️ Scene Production",
        "📺 YouTube",
    ]
)


# =========================================================
# HOME
# =========================================================

with nav[0]:
    st.header("What would you like to do?")

    if project:
        st.markdown("## Continue your current episode")
        render_project_card(project)

        c1, c2 = st.columns(2)
        with c1:
            st.button(
                "Continue building this episode",
                type="primary",
                use_container_width=True,
                disabled=False,
            )
        with c2:
            st.caption(
                "Use the tabs above to open the exact part you want. "
                "Nothing is locked behind a production line."
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

        search = st.text_input(
            "Search the catalogue",
            placeholder="Example: Daniel, Esther, Moses, Ruth...",
        )

        rows = list_catalog_people(
            search=search,
            limit=30,
        )

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
                st.session_state.project_id = pid
                st.success("Episode created.")
                st.rerun()
        else:
            st.warning("No matching story was found.")

        with st.expander("Browse series ideas"):
            for item in list_series():
                st.markdown(f"**{item['series_name']}**")
                if item.get("core_concept"):
                    st.write(item["core_concept"])
                if item.get("best_starter_episodes"):
                    st.caption(
                        "Good starting episodes: "
                        + str(item["best_starter_episodes"])
                    )
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
# STORY & SCRIPT
# =========================================================

with nav[1]:
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

        step = st.radio(
            "Choose what you want to work on",
            [
                "1. Shape the story",
                "2. Write the script",
                "3. Check viewer retention",
            ],
            horizontal=True,
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
                with st.spinner("Shaping the story..."):
                    develop_treatment(project["id"])
                st.rerun()

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

                with st.expander("See all treatment details"):
                    st.json(treatment)

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

                if st.button(
                    "Write the script"
                    if not script
                    else "Rewrite the script",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Writing the episode..."):
                        draft_script(project["id"])
                    st.rerun()

                show_script(script)

        else:
            if not script:
                st.info("Write the script first.")
            else:
                st.subheader("Check viewer retention")
                st.write(
                    "This checks the hook, pacing, repetition, emotional build and payoff."
                )

                if st.button(
                    "Review the script"
                    if not critique
                    else "Review the script again",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Reviewing the script..."):
                        critique_script(project["id"])
                    st.rerun()

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


# =========================================================
# VISUAL BIBLE
# =========================================================

with nav[2]:
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

        if st.button(
            "Build the Visual Bible"
            if not bible
            else "Rebuild the Visual Bible",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner(
                "Building people, groups, locations and props..."
            ):
                build_character_bible(project["id"])
            st.rerun()

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


# =========================================================
# SCENE PRODUCTION
# =========================================================

with nav[3]:
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

            st.markdown("### Frame prompt")
            st.caption("Use this to generate the still image.")
            st.code(scene.get("frame_prompt") or "", wrap_lines=True)

            st.markdown("### Video prompt")
            st.caption("Use this to animate the approved frame.")
            st.code(scene.get("video_prompt") or "", wrap_lines=True)

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


# =========================================================
# YOUTUBE
# =========================================================

with nav[4]:
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
