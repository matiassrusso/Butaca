from backend.app.db import qmark_to_pyformat


def test_qmark_to_pyformat_translates_all_placeholders():
    sql = "INSERT INTO users (username, password_hash) VALUES (?, ?)"
    assert qmark_to_pyformat(sql) == "INSERT INTO users (username, password_hash) VALUES (%s, %s)"


def test_qmark_to_pyformat_leaves_sql_without_placeholders_unchanged():
    sql = "DELETE FROM sessions WHERE user_id = 1"
    assert qmark_to_pyformat(sql) == sql
