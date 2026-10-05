import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).with_name("toonscripture.db")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS projects(
        id TEXT PRIMARY KEY,
        story_name TEXT NOT NULL,
        bible_reference TEXT,
        target_minutes REAL DEFAULT 6,
        format TEXT DEFAULT 'long_form',
        status TEXT DEFAULT 'idea',
        treatment_json TEXT,
        script_json TEXT,
        critique_json TEXT,
        character_bible_json TEXT,
        scenes_json TEXT,
        package_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS catalog_people(
        id TEXT PRIMARY KEY,
        source_sheet TEXT,
        source_position INTEGER,
        testament TEXT,
        book TEXT,
        name TEXT NOT NULL,
        entity_type TEXT,
        named_status TEXT,
        bible_references TEXT,
        story_role TEXT,
        priority TEXT,
        cinematic_score REAL,
        youtube_hook TEXT,
        reference_asset_need TEXT,
        primary_environment TEXT,
        canon TEXT,
        playlist_series TEXT,
        notes TEXT,
        source_url TEXT,
        imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS catalog_series(
        id TEXT PRIMARY KEY,
        rank INTEGER,
        series_name TEXT UNIQUE NOT NULL,
        series_type TEXT,
        core_concept TEXT,
        best_starter_episodes TEXT,
        youtube_reason TEXT,
        recommended_scene_count TEXT,
        recommended_runtime TEXT,
        priority TEXT,
        status TEXT,
        source_notes TEXT,
        imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS project_catalog_links(
        project_id TEXT PRIMARY KEY,
        catalog_person_id TEXT,
        catalog_series_id TEXT,
        episode_title TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS references_library(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        reference_type TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT DEFAULT 'not_approved',
        master_prompt TEXT,
        identity_lock TEXT,
        negative_lock TEXT,
        image_path TEXT,
        metadata_json TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_id, reference_type, name)
    );
    """)
    con.commit()
    con.close()


def _row(row):
    return dict(row) if row else None


def list_projects():
    con = connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM projects ORDER BY created_at DESC")]
    con.close()
    return rows


def get_project(project_id):
    con = connect()
    row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    con.close()
    return _row(row)


def create_project(story_name, bible_reference="", target_minutes=6.0, fmt="long_form"):
    project_id = str(uuid.uuid4())[:8]
    con = connect()
    con.execute(
        "INSERT INTO projects(id,story_name,bible_reference,target_minutes,format) VALUES(?,?,?,?,?)",
        (project_id, story_name.strip(), bible_reference.strip(), float(target_minutes), fmt),
    )
    con.commit()
    con.close()
    return project_id


def save_json(project_id, field, value, status=None):
    allowed = {
        "treatment_json", "script_json", "critique_json",
        "character_bible_json", "scenes_json", "package_json"
    }
    if field not in allowed:
        raise ValueError(field)
    con = connect()
    if status:
        con.execute(
            f"UPDATE projects SET {field}=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(value), status, project_id),
        )
    else:
        con.execute(
            f"UPDATE projects SET {field}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(value), project_id),
        )
    con.commit()
    con.close()


def load_json(project, field, default=None):
    raw = project.get(field) if project else None
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def catalog_summary():
    con = connect()
    out = {
        "people_total": con.execute("SELECT COUNT(*) FROM catalog_people").fetchone()[0],
        "women_total": con.execute("SELECT COUNT(*) FROM catalog_people WHERE entity_type='woman'").fetchone()[0],
        "men_total": con.execute("SELECT COUNT(*) FROM catalog_people WHERE entity_type='man'").fetchone()[0],
        "high_priority": con.execute("SELECT COUNT(*) FROM catalog_people WHERE priority='High'").fetchone()[0],
        "series_total": con.execute("SELECT COUNT(*) FROM catalog_series").fetchone()[0],
    }
    con.close()
    return out


def list_catalog_people(search="", priority="", entity_type="", playlist="", limit=500):
    clauses, params = [], []
    if search:
        clauses.append("(name LIKE ? OR story_role LIKE ? OR bible_references LIKE ?)")
        q = f"%{search}%"
        params += [q, q, q]
    if priority:
        clauses.append("priority=?")
        params.append(priority)
    if entity_type:
        clauses.append("entity_type=?")
        params.append(entity_type)
    if playlist:
        clauses.append("playlist_series=?")
        params.append(playlist)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
    SELECT * FROM catalog_people {where}
    ORDER BY
      CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
      CASE WHEN cinematic_score IS NULL THEN 1 ELSE 0 END,
      cinematic_score DESC,
      source_position ASC,
      name ASC
    LIMIT ?
    """
    params.append(int(limit))
    con = connect()
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()
    return rows


def list_series():
    con = connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM catalog_series ORDER BY rank ASC, series_name ASC")]
    con.close()
    return rows


def get_catalog_person(person_id):
    con = connect()
    row = con.execute("SELECT * FROM catalog_people WHERE id=?", (person_id,)).fetchone()
    con.close()
    return _row(row)


def link_project(project_id, person_id=None, series_id=None, episode_title=None):
    con = connect()
    con.execute("""
    INSERT INTO project_catalog_links(project_id,catalog_person_id,catalog_series_id,episode_title)
    VALUES(?,?,?,?)
    ON CONFLICT(project_id) DO UPDATE SET
      catalog_person_id=excluded.catalog_person_id,
      catalog_series_id=excluded.catalog_series_id,
      episode_title=excluded.episode_title
    """, (project_id, person_id, series_id, episode_title))
    con.commit()
    con.close()


def import_spreadsheet(file_bytes):
    from io import BytesIO
    from openpyxl import load_workbook
    import hashlib

    wb = load_workbook(BytesIO(file_bytes), data_only=True)
    con = connect()

    def stable(prefix, *parts):
        raw = "|".join(str(p or "").strip().lower() for p in parts)
        return prefix + "_" + hashlib.sha1(raw.encode()).hexdigest()[:12]

    def sheet_rows(name):
        ws = wb[name]
        headers = [str(c.value or "").strip() for c in ws[1]]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(v not in (None, "") for v in row):
                continue
            yield dict(zip(headers, row))

    con.execute("DELETE FROM catalog_people")
    con.execute("DELETE FROM catalog_series")

    if "Master Checklist" in wb.sheetnames:
        for r in sheet_rows("Master Checklist"):
            name = r.get("Woman / Character")
            if not name:
                continue
            cid = stable("person", "Master Checklist", name, r.get("Bible Reference(s)"))
            con.execute("""
            INSERT OR REPLACE INTO catalog_people(
              id,source_sheet,source_position,testament,book,name,entity_type,named_status,
              bible_references,story_role,priority,youtube_hook,reference_asset_need,
              primary_environment,canon,playlist_series,notes,source_url,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """, (
                cid, "Master Checklist", r.get("Order"), r.get("Testament"), r.get("Book"),
                str(name), "woman", r.get("Named Status"), r.get("Bible Reference(s)"),
                r.get("Story / Role"), r.get("Priority"), None, r.get("Reference Asset Need"),
                r.get("Primary Environment"), r.get("Canon"), None, r.get("Notes"), r.get("Source URL")
            ))

    if "Men Ranked" in wb.sheetnames:
        for r in sheet_rows("Men Ranked"):
            name = r.get("Man / Character")
            if not name:
                continue
            cid = stable("person", "Men Ranked", name, r.get("Bible Reference(s)"))
            score = r.get("Cinematic Score")
            try:
                score = float(score) if score not in (None, "") else None
            except Exception:
                score = None
            con.execute("""
            INSERT OR REPLACE INTO catalog_people(
              id,source_sheet,source_position,testament,book,name,entity_type,named_status,
              bible_references,story_role,priority,cinematic_score,youtube_hook,reference_asset_need,
              primary_environment,canon,playlist_series,notes,source_url,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """, (
                cid, "Men Ranked", r.get("Rank"), r.get("Testament"), r.get("Book"),
                str(name), "man", r.get("Named Status"), r.get("Bible Reference(s)"),
                r.get("Story / Role"), r.get("Priority"), score, r.get("YouTube Hook"),
                r.get("Reference Asset Need"), r.get("Primary Environment"), r.get("Canon"),
                r.get("Playlist / Series"), r.get("Notes"), r.get("Source URL")
            ))

    if "Series Playlists" in wb.sheetnames:
        for r in sheet_rows("Series Playlists"):
            name = r.get("Series / Playlist")
            if not name:
                continue
            sid = stable("series", name)
            con.execute("""
            INSERT OR REPLACE INTO catalog_series(
              id,rank,series_name,series_type,core_concept,best_starter_episodes,youtube_reason,
              recommended_scene_count,recommended_runtime,priority,status,source_notes,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """, (
                sid, r.get("Rank"), str(name), r.get("Type"), r.get("Core Concept"),
                r.get("Best Starter Episodes"), r.get("Why It Can Work on YouTube"),
                r.get("Recommended Scene Count"), r.get("Recommended Runtime"),
                r.get("Priority"), r.get("Status"), r.get("Source / Notes")
            ))

    con.commit()
    con.close()
    return catalog_summary()
