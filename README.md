# ToonScripture OS

ToonScripture OS is a database-backed production dashboard for cinematic 3D Bible-story videos.

## Current structure

- `app.py` — Streamlit user interface
- `db.py` — SQLite database and spreadsheet catalogue import
- `workflow.py` — Gemini-powered treatment, script, critique, visual bible, scene and YouTube packaging workflow
- `requirements.txt` — runtime dependencies
- `.env.example` — environment variable names only, no secrets

## User flow

Home → choose/import catalogue story → create episode → Treatment → Script → Retention Review → Visual Bible → Production Scenes → YouTube Package.

The Visual Bible supports:

- major recurring characters
- recurring supporting characters
- group / uniform systems
- creature groups
- locations
- props

Scene production follows a strict continuity structure:

**Start state → dominant action → end state**

with physical/spatial constraints and negative constraints.

## Database

The app uses SQLite through `toonscripture.db`.

If the database does not yet contain the imported planning catalogue, the Home screen lets the user upload the existing `.xlsx` planning spreadsheet once. The app imports it into the database directly — no terminal workflow is required.

## Secrets

Do not commit API keys.

For deployment, add `GEMINI_API_KEY` in the hosting platform's secrets/environment settings. The app can also read `GEMINI_API_KEY_A`, `GEMINI_API_KEY_B`, etc.

## Run

The application entry point is:

```
streamlit run app.py
```

The intended user workflow is through the browser interface, not through Terminal.
