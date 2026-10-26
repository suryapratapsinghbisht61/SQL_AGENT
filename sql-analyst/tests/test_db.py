from app import db
from app.config import settings


def test_schema_text(live_db):
    schema = db.get_schema_text()
    assert "track(" in schema and "track_id INTEGER PK" in schema
    assert "FK track(album_id) -> album(album_id)" in schema


def test_run_query_row_limit(live_db):
    columns, rows = db.run_query("SELECT track_id, name FROM track")
    assert columns == ["track_id", "name"]
    assert len(rows) == settings.row_limit
    assert set(rows[0]) == {"track_id", "name"}
