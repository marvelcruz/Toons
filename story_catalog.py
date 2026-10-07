import hashlib
import json
from datetime import datetime, timezone

import db as storage


def _stable_id(prefix, *parts):
    raw = "|".join(str(part or "").strip().lower() for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _episode_count(value):
    try:
        count = int(value)
    except Exception:
        count = 1
    return max(1, min(3, count))


def ensure_local_story_schema():
    if storage.using_supabase():
        return

    con = storage._local_connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog_stories(
            id TEXT PRIMARY KEY,
            story_key TEXT UNIQUE NOT NULL,
            story_title TEXT NOT NULL,
            testament TEXT,
            book TEXT,
            bible_references TEXT,
            story_summary TEXT,
            episode_count INTEGER NOT NULL DEFAULT 1,
            structure_type TEXT NOT NULL DEFAULT 'single',
            structure_reason TEXT,
            ai_structure_status TEXT NOT NULL DEFAULT 'analyzed',
            human_override INTEGER NOT NULL DEFAULT 0,
            analysis_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS catalog_story_people(
            story_id TEXT NOT NULL,
            catalog_person_id TEXT NOT NULL,
            relationship_role TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(story_id, catalog_person_id)
        );

        CREATE TABLE IF NOT EXISTS catalog_episodes(
            id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL,
            episode_number INTEGER NOT NULL,
            episode_title TEXT NOT NULL,
            display_title TEXT NOT NULL,
            bible_reference TEXT,
            narrative_scope TEXT,
            hook TEXT,
            conflict TEXT,
            climax TEXT,
            resolution TEXT,
            recommended_runtime_minutes REAL,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_id, episode_number)
        );

        CREATE INDEX IF NOT EXISTS idx_catalog_story_people_person
          ON catalog_story_people(catalog_person_id);

        CREATE INDEX IF NOT EXISTS idx_catalog_episodes_story
          ON catalog_episodes(story_id, episode_number);
        """
    )

    existing = {
        row["name"]
        for row in con.execute("PRAGMA table_info(project_catalog_links)").fetchall()
    }
    if "catalog_story_id" not in existing:
        con.execute(
            "ALTER TABLE project_catalog_links ADD COLUMN catalog_story_id TEXT"
        )
    if "catalog_episode_id" not in existing:
        con.execute(
            "ALTER TABLE project_catalog_links ADD COLUMN catalog_episode_id TEXT"
        )

    con.commit()
    con.close()


def catalog_structure_summary():
    if storage.using_supabase():
        client = storage._client()
        stories = client.table("catalog_stories").select("id,episode_count,ai_structure_status").execute().data or []
        linked = client.table("catalog_story_people").select("catalog_person_id").execute().data or []
        people_total = storage.catalog_summary().get("people_total", 0)
    else:
        ensure_local_story_schema()
        con = storage._local_connect()
        stories = [
            dict(row)
            for row in con.execute(
                "SELECT id, episode_count, ai_structure_status FROM catalog_stories"
            ).fetchall()
        ]
        linked = [
            dict(row)
            for row in con.execute(
                "SELECT catalog_person_id FROM catalog_story_people"
            ).fetchall()
        ]
        people_total = storage.catalog_summary().get("people_total", 0)
        con.close()

    structured_people = len({row.get("catalog_person_id") for row in linked if row.get("catalog_person_id")})
    return {
        "stories_total": len(stories),
        "single_episode": sum(1 for row in stories if int(row.get("episode_count") or 1) == 1),
        "multi_episode": sum(1 for row in stories if int(row.get("episode_count") or 1) > 1),
        "structured_people": structured_people,
        "unstructured_people": max(int(people_total or 0) - structured_people, 0),
    }


def list_catalog_stories(search="", limit=500):
    if storage.using_supabase():
        query = storage._client().table("catalog_stories").select("*")
        if search:
            safe = search.replace("%", "")
            query = query.or_(
                f"story_title.ilike.%{safe}%,"
                f"bible_references.ilike.%{safe}%,"
                f"story_summary.ilike.%{safe}%"
            )
        rows = query.limit(int(limit)).execute().data or []
    else:
        ensure_local_story_schema()
        clauses = []
        params = []
        if search:
            clauses.append(
                "(story_title LIKE ? OR bible_references LIKE ? OR story_summary LIKE ?)"
            )
            q = f"%{search}%"
            params.extend([q, q, q])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(int(limit))
        con = storage._local_connect()
        rows = [
            dict(row)
            for row in con.execute(
                f"SELECT * FROM catalog_stories{where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        ]
        con.close()

    rows.sort(
        key=lambda row: (
            (row.get("book") or "").lower(),
            (row.get("story_title") or "").lower(),
        )
    )
    return rows


def get_catalog_story(story_id):
    if not story_id:
        return None
    if storage.using_supabase():
        result = (
            storage._client()
            .table("catalog_stories")
            .select("*")
            .eq("id", story_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    ensure_local_story_schema()
    con = storage._local_connect()
    row = con.execute(
        "SELECT * FROM catalog_stories WHERE id=?",
        (story_id,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def get_story_for_person(person_id):
    if not person_id:
        return None
    if storage.using_supabase():
        links = (
            storage._client()
            .table("catalog_story_people")
            .select("story_id")
            .eq("catalog_person_id", person_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return get_catalog_story(links[0]["story_id"]) if links else None

    ensure_local_story_schema()
    con = storage._local_connect()
    row = con.execute(
        "SELECT story_id FROM catalog_story_people WHERE catalog_person_id=? LIMIT 1",
        (person_id,),
    ).fetchone()
    con.close()
    return get_catalog_story(row["story_id"]) if row else None


def list_story_episodes(story_id):
    if not story_id:
        return []
    if storage.using_supabase():
        rows = (
            storage._client()
            .table("catalog_episodes")
            .select("*")
            .eq("story_id", story_id)
            .order("episode_number")
            .execute()
            .data
            or []
        )
        return rows

    ensure_local_story_schema()
    con = storage._local_connect()
    rows = [
        dict(row)
        for row in con.execute(
            "SELECT * FROM catalog_episodes WHERE story_id=? ORDER BY episode_number",
            (story_id,),
        ).fetchall()
    ]
    con.close()
    return rows


def list_unstructured_people(limit=50):
    people = storage.list_catalog_people(limit=5000)

    if storage.using_supabase():
        links = (
            storage._client()
            .table("catalog_story_people")
            .select("catalog_person_id")
            .execute()
            .data
            or []
        )
    else:
        ensure_local_story_schema()
        con = storage._local_connect()
        links = [
            dict(row)
            for row in con.execute(
                "SELECT catalog_person_id FROM catalog_story_people"
            ).fetchall()
        ]
        con.close()

    linked = {row.get("catalog_person_id") for row in links}
    return [row for row in people if row.get("id") not in linked][: int(limit)]


def _existing_story_by_key(story_key):
    if storage.using_supabase():
        result = (
            storage._client()
            .table("catalog_stories")
            .select("*")
            .eq("story_key", story_key)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    ensure_local_story_schema()
    con = storage._local_connect()
    row = con.execute(
        "SELECT * FROM catalog_stories WHERE story_key=?",
        (story_key,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def save_story_structure(primary_person, decision):
    if not primary_person:
        raise ValueError("A primary catalog person is required.")
    if not isinstance(decision, dict):
        raise ValueError("Story structure decision must be a dictionary.")

    raw_key = _clean(decision.get("story_key"))
    if not raw_key:
        raw_key = "_".join(
            part.lower().replace(" ", "_")
            for part in [
                _clean(decision.get("story_title")) or primary_person.get("name") or "story",
                _clean(decision.get("bible_references")) or primary_person.get("bible_references") or "",
            ]
            if part
        )
    story_key = rekey = "".join(
        ch if ch.isalnum() or ch == "_" else "_"
        for ch in raw_key.lower()
    ).strip("_")[:120]
    while "__" in story_key:
        story_key = story_key.replace("__", "_")
    if not story_key:
        story_key = _stable_id("story_key", primary_person.get("id"))

    existing = _existing_story_by_key(story_key)
    if existing and bool(existing.get("human_override")):
        return {
            "story": existing,
            "episodes": list_story_episodes(existing["id"]),
            "protected_by_human_override": True,
        }

    count = _episode_count(decision.get("episode_count"))
    episodes = decision.get("episodes") or []
    if not isinstance(episodes, list):
        episodes = []

    normalized_episodes = []
    for index in range(1, count + 1):
        raw = episodes[index - 1] if index - 1 < len(episodes) and isinstance(episodes[index - 1], dict) else {}
        title = _clean(raw.get("episode_title")) or _clean(raw.get("title"))
        if not title:
            title = _clean(decision.get("story_title")) or primary_person.get("name") or f"Episode {index}"
        display_title = title if count == 1 else f"{title} — Part {index}"
        normalized_episodes.append(
            {
                "episode_number": index,
                "episode_title": title,
                "display_title": display_title,
                "bible_reference": _clean(raw.get("bible_reference")) or _clean(raw.get("bible_references")),
                "narrative_scope": _clean(raw.get("narrative_scope")) or _clean(raw.get("scope")),
                "hook": _clean(raw.get("hook")),
                "conflict": _clean(raw.get("conflict")),
                "climax": _clean(raw.get("climax")),
                "resolution": _clean(raw.get("resolution")),
                "recommended_runtime_minutes": raw.get("recommended_runtime_minutes") or raw.get("runtime_minutes"),
            }
        )

    story_id = existing.get("id") if existing else _stable_id("story", story_key)
    story_payload = {
        "id": story_id,
        "story_key": story_key,
        "story_title": _clean(decision.get("story_title")) or primary_person.get("name") or "Untitled story",
        "testament": _clean(decision.get("testament")) or primary_person.get("testament"),
        "book": _clean(decision.get("book")) or primary_person.get("book"),
        "bible_references": _clean(decision.get("bible_references")) or primary_person.get("bible_references"),
        "story_summary": _clean(decision.get("story_summary")) or _clean(decision.get("summary")),
        "episode_count": count,
        "structure_type": "single" if count == 1 else "multipart",
        "structure_reason": _clean(decision.get("structure_reason")) or _clean(decision.get("reason")),
        "ai_structure_status": "analyzed",
        "human_override": False,
        "analysis_json": decision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    requested_people = decision.get("related_person_ids") or []
    if not isinstance(requested_people, list):
        requested_people = []
    requested_people = [str(value) for value in requested_people if value]
    if primary_person.get("id") not in requested_people:
        requested_people.insert(0, primary_person.get("id"))

    all_people = storage.list_catalog_people(limit=5000)
    valid_ids = {row.get("id") for row in all_people}
    related_ids = []
    for person_id in requested_people:
        if person_id in valid_ids and person_id not in related_ids:
            related_ids.append(person_id)

    if storage.using_supabase():
        client = storage._client()
        client.table("catalog_stories").upsert(
            story_payload,
            on_conflict="story_key",
        ).execute()

        client.table("catalog_story_people").delete().eq(
            "story_id", story_id
        ).execute()

        story_people = [
            {
                "story_id": story_id,
                "catalog_person_id": person_id,
                "relationship_role": "primary" if person_id == primary_person.get("id") else "supporting",
                "is_primary": person_id == primary_person.get("id"),
            }
            for person_id in related_ids
        ]
        if story_people:
            client.table("catalog_story_people").upsert(
                story_people,
                on_conflict="story_id,catalog_person_id",
            ).execute()

        client.table("catalog_episodes").delete().eq(
            "story_id", story_id
        ).execute()

        episode_rows = []
        for episode in normalized_episodes:
            episode_rows.append(
                {
                    "id": _stable_id("episode", story_id, episode["episode_number"]),
                    "story_id": story_id,
                    **episode,
                    "status": "planned",
                }
            )
        if episode_rows:
            client.table("catalog_episodes").upsert(
                episode_rows,
                on_conflict="story_id,episode_number",
            ).execute()
    else:
        ensure_local_story_schema()
        con = storage._local_connect()
        con.execute(
            """
            INSERT INTO catalog_stories(
              id, story_key, story_title, testament, book, bible_references,
              story_summary, episode_count, structure_type, structure_reason,
              ai_structure_status, human_override, analysis_json, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(story_key) DO UPDATE SET
              story_title=excluded.story_title,
              testament=excluded.testament,
              book=excluded.book,
              bible_references=excluded.bible_references,
              story_summary=excluded.story_summary,
              episode_count=excluded.episode_count,
              structure_type=excluded.structure_type,
              structure_reason=excluded.structure_reason,
              ai_structure_status=excluded.ai_structure_status,
              analysis_json=excluded.analysis_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                story_id,
                story_key,
                story_payload["story_title"],
                story_payload["testament"],
                story_payload["book"],
                story_payload["bible_references"],
                story_payload["story_summary"],
                count,
                story_payload["structure_type"],
                story_payload["structure_reason"],
                "analyzed",
                0,
                json.dumps(decision),
            ),
        )
        con.execute(
            "DELETE FROM catalog_story_people WHERE story_id=?",
            (story_id,),
        )
        for person_id in related_ids:
            con.execute(
                """
                INSERT OR REPLACE INTO catalog_story_people(
                  story_id, catalog_person_id, relationship_role, is_primary
                ) VALUES(?,?,?,?)
                """,
                (
                    story_id,
                    person_id,
                    "primary" if person_id == primary_person.get("id") else "supporting",
                    1 if person_id == primary_person.get("id") else 0,
                ),
            )

        con.execute(
            "DELETE FROM catalog_episodes WHERE story_id=?",
            (story_id,),
        )
        for episode in normalized_episodes:
            con.execute(
                """
                INSERT INTO catalog_episodes(
                  id, story_id, episode_number, episode_title, display_title,
                  bible_reference, narrative_scope, hook, conflict, climax,
                  resolution, recommended_runtime_minutes, status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    _stable_id("episode", story_id, episode["episode_number"]),
                    story_id,
                    episode["episode_number"],
                    episode["episode_title"],
                    episode["display_title"],
                    episode["bible_reference"],
                    episode["narrative_scope"],
                    episode["hook"],
                    episode["conflict"],
                    episode["climax"],
                    episode["resolution"],
                    episode["recommended_runtime_minutes"],
                    "planned",
                ),
            )
        con.commit()
        con.close()

    story = get_catalog_story(story_id)
    return {
        "story": story,
        "episodes": list_story_episodes(story_id),
        "protected_by_human_override": False,
    }


def set_story_human_override(story_id, enabled=True):
    value = bool(enabled)
    status = "human_override" if value else "analyzed"

    if storage.using_supabase():
        (
            storage._client()
            .table("catalog_stories")
            .update(
                {
                    "human_override": value,
                    "ai_structure_status": status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", story_id)
            .execute()
        )
        return

    ensure_local_story_schema()
    con = storage._local_connect()
    con.execute(
        """
        UPDATE catalog_stories
        SET human_override=?, ai_structure_status=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (1 if value else 0, status, story_id),
    )
    con.commit()
    con.close()


def link_project_to_episode(project_id, story_id=None, episode_id=None):
    if not project_id:
        return

    if storage.using_supabase():
        payload = {
            "catalog_story_id": story_id,
            "catalog_episode_id": episode_id,
        }
        (
            storage._client()
            .table("project_catalog_links")
            .update(payload)
            .eq("project_id", project_id)
            .execute()
        )
        return

    ensure_local_story_schema()
    con = storage._local_connect()
    con.execute(
        """
        UPDATE project_catalog_links
        SET catalog_story_id=?, catalog_episode_id=?
        WHERE project_id=?
        """,
        (story_id, episode_id, project_id),
    )
    con.commit()
    con.close()
