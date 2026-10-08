import json
import io
import wave
import streamlit as st

from db import (
    init_db,
    list_projects,
    get_project,
    create_project,
    set_project_status,
    inferred_project_status,
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
    add_reference_image,
    reference_image_paths,
    get_reference_asset,
    list_reference_assets,
    save_project_asset,
    list_project_assets,
    signed_asset_url,
    save_episode_metrics,
    list_episode_metrics,
    channel_performance_learning,
    ai_usage_today,
    using_supabase,
)
from story_catalog import (
    catalog_structure_summary,
    list_catalog_stories,
    list_story_episodes,
    link_project_to_episode,
)
from workflow import (
    develop_treatment,
    draft_script,
    generate_writer_room,
    synthesize_writer_room,
    critique_script,
    build_character_bible,
    plan_scenes,
    make_package,
    _api_key,
    _api_key_count,
    _openrouter_key,
    _anthropic_key,
    analyze_catalog_batch,
    analyze_catalog_person_structure,
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

# Regional OS-inspired workspace shell:
# quiet chrome, persistent project context, one obvious production line.
st.markdown(
    """
    <style>
    .block-container {
        max-width: 1280px;
        padding-top: 1.4rem;
        padding-bottom: 4rem;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(128,128,128,.16);
    }
    [data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.16);
        border-radius: 14px;
        padding: 12px 14px;
    }
    .ts-eyebrow {
        font-size: .78rem;
        opacity: .62;
        text-transform: uppercase;
        letter-spacing: .08em;
        margin-bottom: .2rem;
    }
    .ts-projectbar {
        border: 1px solid rgba(128,128,128,.18);
        border-radius: 16px;
        padding: 14px 16px;
        margin: .25rem 0 1rem 0;
    }
    .ts-projectbar strong {
        font-size: 1.04rem;
    }
    .ts-next {
        border: 1px solid rgba(128,128,128,.18);
        border-radius: 18px;
        padding: 18px 20px;
        margin: .5rem 0 1rem 0;
    }
    .ts-next-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin-bottom: .25rem;
    }
    .ts-muted {
        opacity: .68;
        font-size: .9rem;
    }
    hr {
        margin-top: 1.2rem !important;
        margin-bottom: 1.2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

MAIN_SECTIONS = [
    "🏠 Home",
    "📋 Story Checklist",
    "✍️ Story & Script",
    "🎨 Visual Bible",
    "🎙️ Audio",
    "🎞️ Scene Production",
    "📺 YouTube",
    "📦 Export",
    "🗃️ Archive",
]

PIPELINE_SECTIONS = [
    "✍️ Story & Script",
    "🎨 Visual Bible",
    "🎙️ Audio",
    "🎞️ Scene Production",
    "📺 YouTube",
    "📦 Export",
]

if "main_section" not in st.session_state:
    st.session_state.main_section = "🏠 Home"

init_db()


# =========================================================
# CLOUD WORKSPACE
# =========================================================

if using_supabase() and not st.session_state.get("_catalog_seed_checked"):
    try:
        seed_catalog_if_empty()
        st.session_state["_catalog_seed_checked"] = True
    except Exception:
        st.warning(
            "Your workspace opened, but the story catalogue could not be prepared automatically. "
            "You can still upload the planning spreadsheet from Home."
        )


# =========================================================
# HELPERS
# =========================================================

def audio_duration_seconds(audio_bytes):
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            if rate:
                return round(frames / rate, 2)
    except Exception:
        pass
    return None


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
    projects = [
        p for p in list_projects()
        if (p.get("status") or "") != "archived"
    ]
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
    return next(p for p in projects if p["id"] == chosen)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("## ToonScripture")
    st.caption("Production OS")

    project = current_project()

    if project:
        done, total = project_progress(project)
        st.markdown(
            f"""
            <div class="ts-projectbar">
                <div class="ts-eyebrow">Current episode</div>
                <strong>{project['story_name']}</strong><br>
                <span class="ts-muted">
                    {project.get('bible_reference') or 'Bible reference not set'} ·
                    {project.get('target_minutes', 0)} min
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(done / total)
        st.caption(f"{done}/{total} production stages prepared")
    else:
        st.caption("No active episode.")

    st.markdown("### Production line")

    if st.button(
        "⌂  Dashboard",
        use_container_width=True,
        type="primary" if st.session_state.main_section == "🏠 Home" else "secondary",
        key="nav_home",
    ):
        st.session_state.main_section = "🏠 Home"
        st.rerun()

    stage_labels = {
        "✍️ Story & Script": "01  Story & Script",
        "🎨 Visual Bible": "02  Visual Bible",
        "🎙️ Audio": "03  Narration Audio",
        "🎞️ Scene Production": "04  Scene Production",
        "📺 YouTube": "05  YouTube Package",
        "📦 Export": "06  Export",
    }

    for section in PIPELINE_SECTIONS:
        if st.button(
            stage_labels[section],
            use_container_width=True,
            type="primary" if st.session_state.main_section == section else "secondary",
            key=f"nav_{section}",
        ):
            st.session_state.main_section = section
            st.rerun()

    st.divider()

    utility_left, utility_right = st.columns(2)
    with utility_left:
        if st.button(
            "Checklist",
            use_container_width=True,
            key="nav_checklist",
        ):
            st.session_state.main_section = "📋 Story Checklist"
            st.rerun()
    with utility_right:
        if st.button(
            "Archive",
            use_container_width=True,
            key="nav_archive",
        ):
            st.session_state.main_section = "🗃️ Archive"
            st.rerun()

    if project:
        with st.expander("Episode actions"):
            st.caption(next_step(project))
            if st.button(
                "Archive current story",
                use_container_width=True,
                key=f"archive_current_story_{project['id']}",
            ):
                set_project_status(project["id"], "archived")
                st.session_state.pop("project_id", None)
                st.session_state.main_section = "🗃️ Archive"
                st.rerun()

    with st.expander("⚙️ System"):
        st.caption(
            "Most people will not need to change anything here."
        )
        st.caption("UI foundation: isolated single-page renderer")

        if _api_key():
            count = _api_key_count()
            st.success("AI tools are connected", icon="✅")
            st.caption(
                f"{count} configured Gemini project"
                + ("s" if count != 1 else "")
            )

            if _openrouter_key():
                st.success("OpenRouter Free AI is connected", icon="✅")
                st.caption("A free OpenRouter model is available as the second AI reviewer.")
            else:
                st.error("OpenRouter Free AI is NOT connected")
                st.caption(
                    "Render is not detecting OPENROUTER_API_KEY in the running service."
                )

            if _anthropic_key():
                st.success("Claude creative writing is connected", icon="✅")
                st.caption(
                    "Claude can join Gemini and OpenRouter in the creative writers' room."
                )
            else:
                st.caption(
                    "Claude is optional. Gemini and OpenRouter Free AI already "
                    "collaborate on scripts and retention without it."
                )

            if "_ai_usage_cache" not in st.session_state:
                st.session_state["_ai_usage_cache"] = ai_usage_today()

            if st.button(
                "Refresh AI activity",
                use_container_width=True,
                key="refresh_api_usage",
            ):
                st.session_state["_ai_usage_cache"] = ai_usage_today()

            usage_rows = {
                row["project_name"]: row
                for row in st.session_state.get("_ai_usage_cache", [])
            }

            st.markdown("### AI provider status")
            st.caption(
                "This shows ToonScripture's recorded calls and last result. "
                "It does not pretend to be Google's exact remaining quota."
            )

            provider_rows = [
                ("Project A · Shape story", "GEMINI_API_KEY_A"),
                ("Project B · Write script", "GEMINI_API_KEY_B"),
                ("Project C · Retention", "GEMINI_API_KEY_C"),
                ("Project D · Spare", "GEMINI_API_KEY_D"),
                ("Project E · Scenes", "GEMINI_API_KEY_E"),
                ("Project F · YouTube", "GEMINI_API_KEY_F"),
                ("Project G · Audio", "GEMINI_API_KEY_G"),
                ("Project H · Frame review", "GEMINI_API_KEY_H"),
                ("Project I · Visual Bible", "GEMINI_API_KEY_I"),
                ("OpenRouter Free AI", "OPENROUTER_FREE_AI"),
                ("Anthropic Claude", "ANTHROPIC_CLAUDE"),
            ]

            for label, key_name in provider_rows:
                row = usage_rows.get(key_name, {})

                if key_name == "OPENROUTER_FREE_AI" and not row:
                    row = usage_rows.get("OPENROUTER_QWEN_FREE", {})

                requests_used = int(row.get("requests", 0) or 0)
                http_status = row.get("last_http_status")
                last_status = row.get("last_status")

                if http_status == 429:
                    state = "LIMIT REACHED"
                elif http_status in (400, 401, 403):
                    state = "KEY / ACCESS ERROR"
                elif http_status == 503:
                    state = "PROVIDER BUSY"
                elif last_status == "success":
                    state = "WORKING"
                elif last_status:
                    state = "ERROR"
                else:
                    state = "NO RECORDED CALLS"

                st.markdown(
                    f"**{label}** · {state}"
                )
                st.caption(
                    f"{requests_used} recorded calls"
                    + (
                        f" · Last section: {row.get('last_section')}"
                        if row.get("last_section")
                        else ""
                    )
                    + (
                        f" · HTTP {http_status}"
                        if http_status is not None
                        else ""
                    )
                )

            st.caption(
                "Gemini daily limits reset at midnight Pacific time. "
                "Access/key errors do not fix themselves by waiting."
            )

            with st.expander("Which AI project does each section use?"):
                st.write("**Shape the story** → Project A")
                st.write("**Write the script** → Project B")
                st.write("**Viewer retention** → Project C")
                st.write("**Visual Bible** → Project I")
                st.write("**Scene Production** → Project E")
                st.write("**YouTube package** → Project F")
                st.write("**Narration Audio** → Project G")
                st.write("**Frame review** → Project H")
                st.write("**Project D** → Reserved spare")
        else:
            st.warning(
                "AI is not configured on the server yet. "
                "Once it is configured, you will not need to paste an API key into ToonScripture."
            )






@st.dialog("Start a new episode", width="large")
def start_new_episode_dialog():
    selected_series_filter = st.session_state.get("selected_series_filter", "")

    if selected_series_filter:
        st.info(f"Showing stories from: {selected_series_filter}")
        if st.button("Show all stories", key="dialog_clear_series_filter"):
            st.session_state.pop("selected_series_filter", None)
            st.rerun()

    search = st.text_input(
        "Search the catalogue",
        placeholder="Example: Daniel, Esther, Moses, Ruth...",
        key="dialog_catalog_search",
    )

    structured = list_catalog_stories(search=search, limit=1000)

    if structured:
        st.markdown("### Production stories")
        structured_choices = {
            row["id"]: (
                f"{row['story_title']} · "
                f"{int(row.get('episode_count') or 1)} episode"
                + ("s" if int(row.get("episode_count") or 1) != 1 else "")
            )
            for row in structured
        }

        story_id = st.selectbox(
            "Choose a structured story",
            list(structured_choices.keys()),
            format_func=lambda sid: structured_choices[sid],
            key="dialog_structured_story",
        )
        selected_story = next(
            row for row in structured if row["id"] == story_id
        )
        episodes = list_story_episodes(story_id)

        if episodes:
            episode_choices = {
                row["id"]: row.get("display_title") or row.get("episode_title")
                for row in episodes
            }
            episode_id = st.selectbox(
                "Choose the episode",
                list(episode_choices.keys()),
                format_func=lambda eid: episode_choices[eid],
                key="dialog_structured_episode",
            )
            selected_episode = next(
                row for row in episodes if row["id"] == episode_id
            )

            st.caption(
                selected_episode.get("narrative_scope")
                or selected_story.get("structure_reason")
                or ""
            )

            episode_title = selected_episode.get("display_title") or selected_episode.get("episode_title")
            bible_reference = (
                selected_episode.get("bible_reference")
                or selected_story.get("bible_references")
                or ""
            )
            recommended = selected_episode.get("recommended_runtime_minutes") or 8
            runtime_options = [4.0, 6.0, 8.0, 10.0, 12.0, 15.0]
            try:
                runtime_default = min(
                    runtime_options,
                    key=lambda value: abs(value - float(recommended)),
                )
            except Exception:
                runtime_default = 8.0

            runtime = st.select_slider(
                "How long should the episode be?",
                options=runtime_options,
                value=runtime_default,
                format_func=lambda x: f"{int(x)} minutes",
                key="dialog_structured_runtime",
            )

            if st.button(
                "Create this structured episode",
                type="primary",
                use_container_width=True,
                key="dialog_create_structured_episode",
            ):
                pid = create_project(
                    episode_title,
                    bible_reference,
                    runtime,
                    "long_form",
                )
                link_project(
                    pid,
                    episode_title=episode_title,
                )
                link_project_to_episode(
                    pid,
                    story_id=story_id,
                    episode_id=episode_id,
                )
                st.session_state.project_id = pid
                st.session_state.main_section = "✍️ Story & Script"
                st.rerun()

        st.divider()

    with st.expander(
        "Character catalogue / stories not structured yet",
        expanded=not bool(structured),
    ):
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
                key="dialog_story_choice",
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

            if st.button(
                "Let Story Architect structure this entry",
                use_container_width=True,
                key="dialog_analyze_story",
            ):
                with st.spinner("Deciding whether this needs one, two or three episodes..."):
                    result = analyze_catalog_person_structure(selected_id)
                story = result.get("story") or {}
                episode_count = int(story.get("episode_count") or 1)
                st.success(
                    f"Structured as {episode_count} episode"
                    + ("s." if episode_count != 1 else ".")
                )
                st.rerun()

            episode_title = st.text_input(
                "Episode title",
                value=selected["name"],
                help="You can still create an episode directly before structuring it.",
                key="dialog_episode_title",
            )
            bible_reference = st.text_input(
                "Bible reference",
                value=selected.get("bible_references") or "",
                key="dialog_bible_reference",
            )
            runtime = st.select_slider(
                "Target length",
                options=[4.0, 6.0, 8.0, 10.0, 12.0, 15.0],
                value=8.0,
                format_func=lambda x: f"{int(x)} minutes",
                key="dialog_runtime",
            )

            if st.button(
                "Create without structuring",
                use_container_width=True,
                key="dialog_create_episode",
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
                set_catalog_production_status(selected_id, "in_progress")
                st.session_state.project_id = pid
                st.session_state.main_section = "✍️ Story & Script"
                st.rerun()
        else:
            st.warning("No matching story was found.")

    st.divider()
    st.markdown("### Or create one manually")

    manual_title = st.text_input(
        "Story title",
        key="dialog_manual_title",
        placeholder="Example: Daniel in the Lions' Den",
    )
    manual_reference = st.text_input(
        "Bible reference",
        key="dialog_manual_reference",
        placeholder="Example: Daniel 6",
    )
    manual_runtime = st.select_slider(
        "Target length",
        options=[4.0, 6.0, 8.0, 10.0, 12.0, 15.0],
        value=8.0,
        format_func=lambda x: f"{int(x)} minutes",
        key="dialog_manual_runtime",
    )

    if st.button(
        "Create manual episode",
        use_container_width=True,
        key="dialog_create_manual",
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
            st.session_state.main_section = "✍️ Story & Script"
            st.rerun()



# =========================================================
# WORKSPACE HEADER
# =========================================================

main_section = st.session_state.main_section

page_names = {
    "🏠 Home": "Dashboard",
    "📋 Story Checklist": "Story Checklist",
    "✍️ Story & Script": "Story & Script",
    "🎨 Visual Bible": "Visual Bible",
    "🎙️ Audio": "Narration Audio",
    "🎞️ Scene Production": "Scene Production",
    "📺 YouTube": "YouTube Package",
    "📦 Export": "Export",
    "🗃️ Archive": "Archive",
}

st.markdown('<div class="ts-eyebrow">ToonScripture OS</div>', unsafe_allow_html=True)
st.title(page_names.get(main_section, "Workspace"))

if project:
    done, total = project_progress(project)
    header_treatment = load_json(project, "treatment_json", {})
    header_researched_refs = header_treatment.get(
        "researched_scripture_references",
        [],
    ) or []
    researched_suffix = (
        f" · +{len(header_researched_refs)} researched Bible references"
        if header_researched_refs
        else ""
    )

    st.markdown(
        f"""
        <div class="ts-projectbar">
            <strong>{project['story_name']}</strong><br>
            <span class="ts-muted">
                {project.get('bible_reference') or 'Bible reference not set'}
                &nbsp;·&nbsp; {project.get('target_minutes', 0)} min
                &nbsp;·&nbsp; {done}/{total} stages prepared
                {researched_suffix}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# SINGLE PAGE RENDER ROOT
# =========================================================
# Every workspace page is rendered inside this one replaceable container.
# This prevents Streamlit from leaving the previous page visible while a
# long-running generation request is in progress.
page_root = st.empty()
page_root.empty()

with page_root.container():
    # =========================================================
    # HOME
    # =========================================================

    if main_section == "🏠 Home":
        if project:
            st.markdown(
                f"""
                <div class="ts-next">
                    <div class="ts-eyebrow">Next action</div>
                    <div class="ts-next-title">{next_step(project)}</div>
                    <div class="ts-muted">
                        Keep moving through the production line. Your episode stays in context.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            next_destination = "✍️ Story & Script"
            if project.get("critique_json") and not project.get("character_bible_json"):
                next_destination = "🎨 Visual Bible"
            elif project.get("character_bible_json") and not list_project_assets(project["id"], "narration_audio"):
                next_destination = "🎙️ Audio"
            elif project.get("character_bible_json") and not project.get("scenes_json"):
                next_destination = "🎞️ Scene Production"
            elif project.get("scenes_json") and not project.get("package_json"):
                next_destination = "📺 YouTube"
            elif project.get("package_json"):
                next_destination = "📦 Export"

            if st.button(
                "Continue production →",
                type="primary",
                use_container_width=True,
                key="dashboard_continue",
            ):
                st.session_state.main_section = next_destination
                st.rerun()

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
            st.markdown("## Start something new")
            st.caption(
                "Episode creation stays on Home and never appears inside production pages."
            )
            if st.button(
                "Start a new episode",
                type="primary",
                use_container_width=True,
                key="open_new_episode_dialog",
            ):
                start_new_episode_dialog()


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

        structure = catalog_structure_summary()
        st.markdown("### Story Architect")
        st.caption(
            "The AI groups character records into production stories and decides "
            "whether each story genuinely needs 1, 2 or 3 episodes."
        )

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Structured stories", structure["stories_total"])
        a2.metric("Single-episode", structure["single_episode"])
        a3.metric("Multi-part", structure["multi_episode"])
        a4.metric("Still to analyze", structure["unstructured_people"])

        batch_col1, batch_col2 = st.columns(2)
        with batch_col1:
            if st.button(
                "Analyze next 10",
                use_container_width=True,
                disabled=structure["unstructured_people"] == 0,
                key="analyze_catalog_10",
            ):
                with st.spinner("Story Architect is updating the catalog..."):
                    results = analyze_catalog_batch(limit=10)
                failures = [row for row in results if not row.get("ok")]
                if failures:
                    st.warning(
                        f"Structured {len(results) - len(failures)} entries; "
                        f"{len(failures)} need another pass."
                    )
                else:
                    st.success(f"Structured {len(results)} catalog entries.")
                st.rerun()

        with batch_col2:
            if st.button(
                "Analyze next 25",
                use_container_width=True,
                disabled=structure["unstructured_people"] == 0,
                key="analyze_catalog_25",
            ):
                with st.spinner("Story Architect is updating the catalog..."):
                    results = analyze_catalog_batch(limit=25)
                failures = [row for row in results if not row.get("ok")]
                if failures:
                    st.warning(
                        f"Structured {len(results) - len(failures)} entries; "
                        f"{len(failures)} need another pass."
                    )
                else:
                    st.success(f"Structured {len(results)} catalog entries.")
                st.rerun()

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
            writer_room = load_json(project, "writer_room_json", {})
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
                            if isinstance(beat, dict):
                                st.write(
                                    "•",
                                    beat.get("beat")
                                    or beat.get("purpose")
                                    or str(beat),
                                )
                            else:
                                st.write("•", beat)

                    researched_refs = treatment.get(
                        "researched_scripture_references",
                        [],
                    ) or []
                    if researched_refs:
                        st.markdown("### Scripture research")
                        st.caption(
                            f"Primary scope: {project.get('bible_reference') or 'Not set'} · "
                            f"{len(researched_refs)} additional relevant passage"
                            + ("s" if len(researched_refs) != 1 else "")
                            + " found through research."
                        )

                        for ref in researched_refs:
                            if not isinstance(ref, dict):
                                st.write("•", ref)
                                continue

                            reference = ref.get("reference") or "Reference"
                            category = (
                                str(ref.get("category") or "")
                                .replace("_", " ")
                                .strip()
                                .title()
                            )
                            relevance = ref.get("relevance") or ""
                            confidence = ref.get("confidence") or ""

                            st.markdown(f"**{reference}**")
                            meta = " · ".join(
                                value
                                for value in [category, str(confidence).title()]
                                if value
                            )
                            if meta:
                                st.caption(meta)
                            if relevance:
                                st.write(relevance)

                    universe = treatment.get("story_universe", {}) or {}
                    series = treatment.get("series_opportunities", []) or []

                    if universe or series:
                        st.markdown("## Story universe")
                        st.caption(
                            "This expands the subject beyond one video. ToonScripture can find "
                            "connected characters, places, events and natural Part 1 / Part 2 / Part 3 stories."
                        )

                        for label, key, title_key in [
                            ("Character threads", "character_threads", "subject"),
                            ("Supporting characters", "supporting_character_threads", "subject"),
                            ("Places & cities", "place_threads", "place"),
                        ]:
                            items = universe.get(key, []) or []
                            if items:
                                st.markdown(f"### {label}")
                                for item in items:
                                    if not isinstance(item, dict):
                                        st.write("•", item)
                                        continue
                                    title = item.get(title_key) or "Untitled"
                                    st.markdown(f"**{title}**")
                                    if item.get("why_it_matters"):
                                        st.write(item["why_it_matters"])
                                    refs = item.get("references", []) or []
                                    if refs:
                                        st.caption("Bible: " + "; ".join(str(x) for x in refs))

                        if series:
                            st.markdown("### Episode opportunities")
                            st.caption(
                                "Create any of these as a separate episode instead of squeezing "
                                "an entire life, city or ministry into one video."
                            )
                            for idx, episode in enumerate(series):
                                if not isinstance(episode, dict):
                                    continue

                                title = (
                                    episode.get("episode_title")
                                    or episode.get("series_title")
                                    or f"Episode {idx + 1}"
                                )
                                part = episode.get("part_number")
                                heading = f"Part {part}: {title}" if part else title
                                st.markdown(f"**{heading}**")

                                if episode.get("focus"):
                                    st.write(episode["focus"])

                                refs = episode.get("bible_references", []) or []
                                if refs:
                                    st.caption(
                                        "Bible: "
                                        + "; ".join(str(x) for x in refs)
                                    )

                                people = episode.get("key_characters", []) or []
                                places = episode.get("key_places", []) or []
                                meta = []
                                if people:
                                    meta.append(
                                        "People: " + ", ".join(str(x) for x in people)
                                    )
                                if places:
                                    meta.append(
                                        "Places: " + ", ".join(str(x) for x in places)
                                    )
                                if meta:
                                    st.caption(" · ".join(meta))

                                reason = episode.get(
                                    "why_this_deserves_its_own_episode"
                                )
                                if reason:
                                    st.caption(reason)

                                runtime = episode.get(
                                    "recommended_runtime_minutes",
                                    8,
                                )
                                try:
                                    runtime = float(runtime)
                                except Exception:
                                    runtime = 8.0

                                if st.button(
                                    f"Create this episode → {title}",
                                    use_container_width=True,
                                    key=(
                                        f"create_story_universe_episode_"
                                        f"{project['id']}_{idx}"
                                    ),
                                ):
                                    new_pid = create_project(
                                        title,
                                        "; ".join(str(x) for x in refs),
                                        runtime,
                                        "long_form",
                                    )
                                    st.session_state.project_id = new_pid
                                    st.session_state.main_section = "✍️ Story & Script"
                                    st.session_state.pop("story_step", None)
                                    st.rerun()

                    with st.expander("See full treatment"):
                        if treatment.get("core_story"):
                            st.markdown("### Core story")
                            st.write(treatment["core_story"])

                        if treatment.get("scriptural_anchor"):
                            st.markdown("### Scriptural anchors")
                            for item in treatment["scriptural_anchor"]:
                                st.write("•", item)

                        if treatment.get("researched_scripture_references"):
                            st.markdown("### Expanded Bible references")
                            for ref in treatment["researched_scripture_references"]:
                                if isinstance(ref, dict):
                                    st.markdown(
                                        f"**{ref.get('reference') or 'Reference'}**"
                                    )
                                    if ref.get("use_in_story"):
                                        st.write(ref["use_in_story"])
                                else:
                                    st.write("•", ref)

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
                        "Create the story treatment first so the writers' room has a clear direction."
                    )
                else:
                    st.subheader("AI Writers' Room")
                    st.write(
                        "Gemini, Claude and OpenRouter each write the full episode independently. "
                        "Then they are scored blind before you move to the master script."
                    )
                    st.caption(
                        "Background active: tested 7,325-line Bible storytelling transcript corpus + "
                        "the extracted step-by-step writing playbook. The corpus guides craft, not Scripture facts."
                    )

                    writer_error = None

                    if not writer_room.get("providers"):
                        if st.button(
                            "Generate the 3 scripts",
                            type="primary",
                            use_container_width=True,
                            key="generate_writer_room",
                        ):
                            try:
                                with st.spinner(
                                    "Gemini, Claude and OpenRouter are each writing their own full script..."
                                ):
                                    generate_writer_room(project["id"])
                                st.rerun()
                            except Exception as exc:
                                writer_error = str(exc)
                    else:
                        if st.button(
                            "Regenerate all 3 scripts",
                            use_container_width=True,
                            key="regenerate_writer_room",
                        ):
                            try:
                                with st.spinner(
                                    "Reopening the room and creating three fresh drafts..."
                                ):
                                    generate_writer_room(project["id"])
                                st.rerun()
                            except Exception as exc:
                                writer_error = str(exc)

                    if writer_error:
                        st.error(
                            "The writers' room could not finish all of its work right now. "
                            "Any drafts that were successfully saved are still safe."
                        )
                        with st.expander("Technical details"):
                            st.code(writer_error)

                    providers = writer_room.get("providers", {}) or {}
                    scorecards = writer_room.get("scorecards", {}) or {}

                    if providers:
                        st.markdown("### The three drafts")
                        st.caption(
                            "These are the untouched individual drafts. The score is the blind jury average."
                        )

                        columns = st.columns(3)
                        provider_order = [
                            ("gemini", "Gemini"),
                            ("claude", "Claude"),
                            ("openrouter", "OpenRouter"),
                        ]

                        for col, (provider_key, provider_label) in zip(
                            columns,
                            provider_order,
                        ):
                            with col:
                                item = providers.get(provider_key, {}) or {}
                                card = scorecards.get(provider_key, {}) or {}
                                candidate_script = item.get("script")
                                average_score = card.get("average_score")

                                st.markdown(f"## {provider_label}")
                                if average_score is not None:
                                    st.metric(
                                        "Blind jury score",
                                        f"{float(average_score):.1f}/100",
                                    )
                                elif candidate_script:
                                    st.caption("Draft created · score unavailable")

                                if candidate_script:
                                    with st.expander(
                                        f"Why the jury scored {provider_label} this way",
                                        expanded=False,
                                    ):
                                        strengths = card.get("strengths", []) or []
                                        weaknesses = card.get("weaknesses", []) or []
                                        standout = card.get("standout_elements", []) or []

                                        if strengths:
                                            st.markdown("**Strengths**")
                                            for value in strengths[:6]:
                                                st.write("•", value)
                                        if weaknesses:
                                            st.markdown("**Weaknesses**")
                                            for value in weaknesses[:6]:
                                                st.write("•", value)
                                        if standout:
                                            st.markdown("**Standout material**")
                                            for value in standout[:6]:
                                                st.write("•", value)

                                        judge_scores = card.get("judge_scores", []) or []
                                        if judge_scores:
                                            st.markdown("**Individual jury scores**")
                                            for row in judge_scores:
                                                st.caption(
                                                    f"{str(row.get('judge') or '').title()}: "
                                                    f"{float(row.get('score_100') or 0):.1f}/100"
                                                )

                                    show_script(candidate_script)
                                else:
                                    st.warning(
                                        item.get("error")
                                        or f"{provider_label} did not return a usable script."
                                    )

                        st.divider()

                        if writer_room.get("status") != "master_ready":
                            st.markdown("### Ready to combine the room?")
                            st.write(
                                "The next pass will mine the strongest hook, structure, emotional beats, "
                                "Scripture-grounded explanations, transitions, dialogue and ending from "
                                "all usable drafts, then rewrite them into one coherent master script."
                            )

                            if st.button(
                                "Next → Build the crème de la crème",
                                type="primary",
                                use_container_width=True,
                                key="build_master_script",
                            ):
                                try:
                                    with st.spinner(
                                        "Comparing the three scripts and building the master version..."
                                    ):
                                        synthesize_writer_room(project["id"])
                                    st.rerun()
                                except Exception as exc:
                                    st.error(
                                        "The master-editor pass could not finish right now. "
                                        "Your three scored drafts are still saved."
                                    )
                                    with st.expander("Technical details"):
                                        st.code(str(exc))

                    if writer_room.get("status") == "master_ready":
                        blueprint = writer_room.get("editorial_blueprint", {}) or {}
                        master_script = (
                            writer_room.get("final_script")
                            or script
                            or {}
                        )

                        st.divider()
                        st.markdown("## What the final script drew from the room")
                        if blueprint.get("overall_strategy"):
                            st.write(blueprint["overall_strategy"])

                        source_map = blueprint.get("elements_taken_from_each", {}) or {}
                        source_cols = st.columns(3)
                        for col, (provider_key, provider_label) in zip(
                            source_cols,
                            [
                                ("gemini", "From Gemini"),
                                ("claude", "From Claude"),
                                ("openrouter", "From OpenRouter"),
                            ],
                        ):
                            with col:
                                st.markdown(f"### {provider_label}")
                                values = source_map.get(provider_key, []) or []
                                if values:
                                    for value in values:
                                        st.write("•", value)
                                else:
                                    st.caption("No specific contribution was called out.")

                        highlights = [
                            ("Best hook", "best_hook_source"),
                            ("Best structure", "best_structure_source"),
                            ("Best emotional work", "best_emotional_source"),
                            ("Best accuracy work", "best_accuracy_source"),
                            ("Best retention work", "best_retention_source"),
                        ]
                        st.markdown("### Editorial decisions")
                        for label, key in highlights:
                            value = blueprint.get(key)
                            if value:
                                st.write(f"**{label}:** {value}")

                        conflicts = blueprint.get("conflicts_resolved", []) or []
                        if conflicts:
                            with st.expander("Conflicts the master editor resolved"):
                                for value in conflicts:
                                    st.write("•", value)

                        plan = blueprint.get("master_plan", []) or []
                        if plan:
                            with st.expander("Master plan"):
                                for value in plan:
                                    st.write("•", value)

                        st.divider()
                        st.markdown("## Final master script")
                        show_script(master_script)

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
                        lower_error = review_error.lower()

                        if "openrouter" in lower_error and "429" in lower_error:
                            st.warning(
                                "OpenRouter's free provider pool is temporarily rate-limited. "
                                "Your script is safe. ToonScripture has already tried several free providers, "
                                "so retry in a little while or continue to the Visual Bible."
                            )
                        elif "api key" in lower_error or "access" in lower_error or "403" in lower_error:
                            st.warning(
                                "The assigned Gemini project has a key or access problem. "
                                "Your script is safe. OpenRouter will still be tried automatically."
                            )
                        elif "quota" in lower_error or "429" in lower_error:
                            st.warning(
                                "The assigned Gemini project's current quota is exhausted. "
                                "Your script is safe. OpenRouter will still be tried automatically."
                            )
                        else:
                            st.error(
                                "Neither Gemini nor OpenRouter produced a usable retention review right now. "
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

                        target = int(critique.get("quality_target", 95) or 95)
                        passed = bool(
                            critique.get(
                                "quality_gate_passed",
                                int(score or 0) >= target,
                            )
                        )

                        attempts = critique.get("review_attempts", []) or []
                        rewrite_rounds = int(
                            critique.get("automatic_rewrite_rounds", 0) or 0
                        )

                        if passed:
                            st.success(
                                f"Retention quality gate passed: {int(score)}/100."
                            )
                        else:
                            st.warning(
                                f"Retention quality gate not passed yet. "
                                f"ToonScripture requires at least {target}/100 before Visual Bible."
                            )

                        if attempts:
                            attempt_text = " → ".join(
                                str(item.get("score", "?"))
                                for item in attempts
                            )
                            st.caption(
                                f"Review path: {attempt_text}"
                                + (
                                    f" · {rewrite_rounds} automatic rewrite round"
                                    + ("s" if rewrite_rounds != 1 else "")
                                    if rewrite_rounds
                                    else ""
                                )
                            )

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

                        if passed:
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
                        else:
                            st.caption(
                                "The script has been improved automatically, but the honest critic "
                                "still scored it below 95. Run the review again to continue improving it."
                            )
                            if st.button(
                                "Improve again toward 95+",
                                type="primary",
                                use_container_width=True,
                                key="improve_again_retention",
                            ):
                                try:
                                    with st.spinner(
                                        "Improving the script and checking retention again..."
                                    ):
                                        critique_script(project["id"])
                                    st.rerun()
                                except Exception as exc:
                                    st.error(
                                        "The improvement pass could not finish right now. "
                                        "Your best saved script is still safe."
                                    )
                                    with st.expander("Technical details"):
                                        st.code(str(exc))


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
                categories = [
                    (
                        "Characters",
                        "characters",
                        "master_character_prompt",
                        "identity_lock",
                    ),
                    (
                        "Supporting characters",
                        "supporting_characters",
                        "master_character_prompt",
                        "identity_lock",
                    ),
                    (
                        "Groups & uniforms",
                        "character_groups",
                        "master_group_prompt",
                        "group_identity_lock",
                    ),
                    (
                        "Locations",
                        "locations",
                        "master_environment_prompt",
                        "environment_lock",
                    ),
                    (
                        "Props",
                        "props",
                        "master_prop_prompt",
                        None,
                    ),
                ]

                total_items = sum(
                    len(bible.get(key, []) or [])
                    for _, key, _, _ in categories
                )
                reference_rows = list_reference_assets(project["id"])
                reference_lookup = {
                    (row.get("reference_type"), row.get("name")): row
                    for row in reference_rows
                }
                approved_items = len(reference_rows)

                st.markdown("## Complete Visual Bible")
                st.write(
                    f"**{total_items} visual references found** · "
                    f"**{approved_items} approved** · "
                    f"**{max(total_items - approved_items, 0)} still need review**"
                )
                if total_items:
                    st.progress(
                        approved_items / total_items,
                        text=f"{approved_items} of {total_items} references approved",
                    )

                st.caption(
                    "Everything is shown below in one continuous sheet. "
                    "Each subject can have a primary continuity image plus as many supporting "
                    "references as you need. Add more at any point in production."
                )
                st.divider()

                for category_label, key, prompt_key, lock_key in categories:
                    items = bible.get(key, []) or []

                    st.markdown(f"# {category_label}")
                    if not items:
                        st.caption("No entries were created in this section.")
                        st.divider()
                        continue

                    for item_index, item in enumerate(items):
                        selected_name = (
                            item.get("name")
                            or f"{category_label.rstrip('s')} {item_index + 1}"
                        )

                        st.markdown(f"## {selected_name}")

                        role = (
                            item.get("role")
                            or item.get("story_function")
                            or item.get("story_purpose")
                        )
                        if role:
                            st.write(role)

                        # Show useful descriptive fields directly instead of hiding
                        # them in JSON or dropdowns.
                        hidden_fields = {
                            "name",
                            "role",
                            "story_function",
                            "story_purpose",
                            prompt_key,
                            lock_key,
                            "negative_identity_lock",
                            "negative_group_lock",
                            "allowed_individual_variation",
                        }

                        for field_name, field_value in item.items():
                            if field_name in hidden_fields:
                                continue
                            if field_value in (None, "", [], {}):
                                continue

                            label = field_name.replace("_", " ").strip().title()
                            st.markdown(f"**{label}**")

                            if isinstance(field_value, list):
                                for value in field_value:
                                    st.write("•", value)
                            elif isinstance(field_value, dict):
                                for sub_key, sub_value in field_value.items():
                                    sub_label = (
                                        str(sub_key)
                                        .replace("_", " ")
                                        .strip()
                                        .title()
                                    )
                                    st.write(f"**{sub_label}:** {sub_value}")
                            else:
                                st.write(field_value)

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
                            variation = item.get(
                                "allowed_individual_variation",
                                [],
                            )
                            if variation:
                                st.markdown(
                                    "### What may vary between members"
                                )
                                for value in variation:
                                    st.write("•", value)

                        st.markdown("### Reference board")
                        saved_reference = reference_lookup.get(
                            (key, selected_name)
                        )

                        reference_paths = reference_image_paths(saved_reference)
                        reference_urls = []
                        for path in reference_paths:
                            try:
                                url = signed_asset_url(path)
                            except Exception:
                                url = None
                            if url:
                                reference_urls.append(url)

                        if reference_urls:
                            st.caption(
                                f"{len(reference_urls)} approved reference image"
                                + ("s" if len(reference_urls) != 1 else "")
                                + " saved for continuity."
                            )
                            ref_columns = st.columns(min(3, len(reference_urls)))
                            for ref_index, ref_url in enumerate(reference_urls):
                                with ref_columns[ref_index % len(ref_columns)]:
                                    st.image(
                                        ref_url,
                                        caption=(
                                            "Primary reference"
                                            if ref_index == 0
                                            else f"Reference {ref_index + 1}"
                                        ),
                                        use_container_width=True,
                                    )
                        else:
                            st.caption(
                                "No approved images yet. Generate references in Google Flow "
                                "or add any approved images you already have."
                            )

                        if not saved_reference:
                            uploaded_reference = st.file_uploader(
                                f"Upload the primary reference for {selected_name}",
                                type=["png", "jpg", "jpeg", "webp"],
                                key=(
                                    f"reference_upload_{project['id']}_"
                                    f"{key}_{item_index}"
                                ),
                            )

                            if uploaded_reference and st.button(
                                f"Set primary reference for {selected_name}",
                                type="primary",
                                use_container_width=True,
                                key=(
                                    f"save_reference_{project['id']}_"
                                    f"{key}_{item_index}"
                                ),
                            ):
                                with st.spinner(
                                    f"Saving {selected_name} as the primary reference..."
                                ):
                                    save_reference_asset(
                                        project_id=project["id"],
                                        reference_type=key,
                                        name=selected_name,
                                        file_bytes=uploaded_reference.getvalue(),
                                        filename=uploaded_reference.name,
                                        content_type=(
                                            uploaded_reference.type
                                            or "application/octet-stream"
                                        ),
                                        master_prompt=prompt,
                                        identity_lock=(
                                            item.get(lock_key)
                                            if lock_key
                                            else None
                                        ),
                                        negative_lock=(
                                            item.get("negative_identity_lock")
                                            or item.get("negative_group_lock")
                                        ),
                                    )
                                st.success("Primary reference saved.")
                                st.rerun()
                        else:
                            st.success(
                                "Primary reference locked. You can keep adding supporting references."
                            )

                        extra_references = st.file_uploader(
                            f"Add more references for {selected_name}",
                            type=["png", "jpg", "jpeg", "webp"],
                            accept_multiple_files=True,
                            key=(
                                f"extra_reference_upload_{project['id']}_"
                                f"{key}_{item_index}"
                            ),
                            help=(
                                "Add alternate angles, expressions, costumes, lighting studies, "
                                "prop details or environment views. These do not replace the primary image."
                            ),
                        )

                        if extra_references and st.button(
                            f"Add {len(extra_references)} reference"
                            + ("s" if len(extra_references) != 1 else ""),
                            use_container_width=True,
                            key=(
                                f"add_reference_{project['id']}_"
                                f"{key}_{item_index}"
                            ),
                        ):
                            with st.spinner(
                                f"Adding references to {selected_name}..."
                            ):
                                for uploaded in extra_references:
                                    add_reference_image(
                                        project_id=project["id"],
                                        reference_type=key,
                                        name=selected_name,
                                        file_bytes=uploaded.getvalue(),
                                        filename=uploaded.name,
                                        content_type=(
                                            uploaded.type
                                            or "application/octet-stream"
                                        ),
                                    )
                            st.success("Additional references added.")
                            st.rerun()

                        st.divider()

            if bible:
                st.divider()
                st.button(
                    "Next → Narration Audio",
                    type="primary",
                    use_container_width=True,
                    key="next_to_audio_from_bible",
                    on_click=go_to_main_section,
                    args=("🎙️ Audio",),
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

            scene_error = None

            if st.button(
                "Build scene prompts"
                if not scenes
                else "Rebuild scene prompts",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner("Breaking the story into production scenes..."):
                        plan_scenes(project["id"])
                    st.rerun()
                except Exception as exc:
                    scene_error = str(exc)

            if scene_error:
                st.error(
                    "The scene plan could not be rebuilt right now. "
                    "Your episode is still safe."
                )
                with st.expander("Technical details"):
                    st.code(scene_error)

            if scenes:
                total_seconds = sum(
                    int(scene.get("duration_seconds") or 0)
                    for scene in scenes
                )
                target_seconds = int(
                    round(float(project.get("target_minutes") or 0) * 60)
                )

                st.markdown("### Full episode scene plan")
                st.write(
                    f"**{len(scenes)} scenes** · "
                    f"**{total_seconds // 60}:{total_seconds % 60:02d} planned** "
                    f"of **{target_seconds // 60}:{target_seconds % 60:02d} target**"
                )
                st.caption(
                    "Flow clip lengths are locked to 4, 5, 8 or 10 seconds. "
                    "All scenes are listed below in story order."
                )

                if target_seconds and abs(total_seconds - target_seconds) > 15:
                    st.warning(
                        "The current scene timing does not closely match the episode runtime. "
                        "Click Rebuild scene prompts before production."
                    )

                scene_bible = load_json(
                    project,
                    "character_bible_json",
                    {},
                )
                scene_reference_rows = list_reference_assets(project["id"])
                scene_reference_lookup = {
                    (row.get("reference_type"), row.get("name")): row
                    for row in scene_reference_rows
                }

                for i, scene in enumerate(scenes):
                    scene_number = scene.get("scene_number", i + 1)
                    scene_title = scene.get("scene_title") or "Untitled"
                    duration = int(scene.get("duration_seconds") or 0)
                    label = (
                        f"Scene {scene_number} · {scene_title} · {duration} sec"
                    )

                    with st.expander(label):
                        if scene.get("narration"):
                            st.markdown("**Narration**")
                            st.write(scene["narration"])

                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.markdown("**Start**")
                            st.write(scene.get("start_state") or "—")
                        with c2:
                            st.markdown("**Action**")
                            st.write(scene.get("dominant_action") or "—")
                        with c3:
                            st.markdown("**End**")
                            st.write(scene.get("end_state") or "—")

                        scene_package = compose_scene_package(
                            project["id"],
                            scene,
                            project=project,
                            bible=scene_bible,
                            saved_lookup=scene_reference_lookup,
                        )

                        st.markdown("**Frame prompt**")
                        st.code(
                            scene_package.get("frame_prompt") or "",
                            wrap_lines=True,
                        )

                        st.markdown("**Video prompt**")
                        st.code(
                            scene_package.get("video_prompt") or "",
                            wrap_lines=True,
                        )

                        constraints = scene.get("physical_constraints", [])
                        negatives = scene.get("negative_constraints", [])
                        if constraints or negatives:
                            st.markdown("**Rules**")
                            for item in constraints:
                                st.write("•", item)
                            for item in negatives:
                                st.write("• Do not:", item)

                        frame_upload = st.file_uploader(
                            f"Upload generated frame for Scene {scene_number}",
                            type=["png", "jpg", "jpeg", "webp"],
                            key=f"scene_frame_{project['id']}_{scene_number}",
                        )

                        if frame_upload and st.button(
                            f"Check Scene {scene_number} frame",
                            type="primary",
                            use_container_width=True,
                            key=f"review_frame_{project['id']}_{scene_number}",
                        ):
                            with st.spinner(
                                f"Checking Scene {scene_number}..."
                            ):
                                review = review_scene_frame(
                                    project["id"],
                                    scene,
                                    frame_upload.getvalue(),
                                    frame_upload.type or "image/png",
                                )
                            st.session_state[
                                f"review_result_{project['id']}_{scene_number}"
                            ] = review

                        review = st.session_state.get(
                            f"review_result_{project['id']}_{scene_number}"
                        )
                        if review:
                            verdict = review.get("verdict", "")
                            score = review.get("overall_score")
                            st.write(
                                f"Review: {verdict or 'complete'}"
                                + (
                                    f" · {score}/100"
                                    if score is not None
                                    else ""
                                )
                            )


            if scenes:
                st.divider()
                st.button(
                    "Next → YouTube",
                    type="primary",
                    use_container_width=True,
                    key="next_to_youtube_from_scenes",
                    on_click=go_to_main_section,
                    args=("📺 YouTube",),
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
                                    "duration_seconds": audio_duration_seconds(
                                        audio_bytes
                                    ),
                                    "word_count": len(
                                        full_narration.split()
                                    ),
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
                        "Next → Scene Production",
                        type="primary",
                        use_container_width=True,
                        key="next_to_scene_production_from_audio",
                        on_click=go_to_main_section,
                        args=("🎞️ Scene Production",),
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

            st.divider()
            st.markdown("## What ToonScripture is learning")
            learning = channel_performance_learning()

            episode_count = int(learning.get("episode_count", 0) or 0)
            confidence = learning.get("confidence") or "no_data"

            if episode_count == 0:
                st.caption(
                    "No channel lessons yet. Save performance after publishing episodes "
                    "and future treatments/scripts will begin using the evidence."
                )
            else:
                st.write(
                    f"**{episode_count} published episode"
                    + ("s" if episode_count != 1 else "")
                    + f" in the learning set · confidence: {confidence}**"
                )

                if confidence == "early":
                    st.caption(
                        "The sample is still small, so ToonScripture will treat these as observations, "
                        "not rules."
                    )
                elif confidence == "emerging":
                    st.caption(
                        "Patterns are starting to form, but they are still treated as hypotheses."
                    )
                else:
                    st.caption(
                        "There is enough history for ToonScripture to use repeated patterns more deliberately."
                    )

                for lesson in learning.get("lessons", []):
                    st.write("•", lesson)

                notes = learning.get("notes", [])
                if notes:
                    st.markdown("**Your saved observations**")
                    for note in notes:
                        st.write(
                            f"• {note.get('story_name')}: {note.get('note')}"
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
                export_bible = load_json(
                    project,
                    "character_bible_json",
                    {},
                )
                export_reference_rows = list_reference_assets(project["id"])
                export_reference_lookup = {
                    (row.get("reference_type"), row.get("name")): row
                    for row in export_reference_rows
                }
                for scene in scene_list:
                    package = compose_scene_package(
                        project["id"],
                        scene,
                        project=project,
                        bible=export_bible,
                        saved_lookup=export_reference_lookup,
                    )
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

            st.divider()
            st.markdown("### Not ready to publish this yet?")
            st.caption(
                "Archive this episode to remove it from your active workspace. "
                "All scripts, scenes, references and exports stay saved."
            )
            if st.button(
                "Archive this story",
                use_container_width=True,
                key=f"archive_story_{project['id']}",
            ):
                set_project_status(project["id"], "archived")
                st.session_state.pop("project_id", None)
                st.session_state.main_section = "🗃️ Archive"
                st.rerun()

            st.divider()
            st.markdown("### Ready for the next story?")
            st.caption(
                "Start another Bible story without leaving the workflow."
            )
            if st.button(
                "Start next story",
                type="primary",
                use_container_width=True,
                key=f"start_next_story_{project['id']}",
            ):
                start_new_episode_dialog()

    # =========================================================
    # ARCHIVE
    # =========================================================

    if main_section == "🗃️ Archive":
        st.header("Story Archive")
        st.write(
            "Park episodes here when you are not ready to publish or continue them yet. "
            "Nothing is deleted."
        )

        archived_projects = [
            p for p in list_projects()
            if (p.get("status") or "") == "archived"
        ]

        if not archived_projects:
            st.info("No archived stories yet.")
        else:
            st.caption(f"{len(archived_projects)} archived stories")

            for archived in archived_projects:
                st.markdown(f"### {archived['story_name']}")
                st.caption(
                    f"{archived.get('bible_reference') or 'Bible reference not set'} · "
                    f"{archived.get('target_minutes', 0)} min"
                )

                done, total = project_progress(archived)
                st.progress(
                    done / total if total else 0,
                    text=f"{done} of {total} preparation stages complete",
                )

                if st.button(
                    "Restore to active workspace",
                    type="primary",
                    use_container_width=True,
                    key=f"restore_archived_{archived['id']}",
                ):
                    set_project_status(
                        archived["id"],
                        inferred_project_status(archived),
                    )
                    st.session_state.project_id = archived["id"]
                    st.session_state.main_section = "🏠 Home"
                    st.rerun()

                st.divider()

