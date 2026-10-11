# expect: code_generation, sql_generation -- three plain helpers and one function that runs an UPDATE; the docstring's SQL and the lowercase English log text are not SQL.
import logging
import sqlite3

log = logging.getLogger(__name__)


def normalise_email(raw: str) -> str:
    return raw.strip().lower()


def is_valid_email(address: str) -> bool:
    local, _, domain = address.partition("@")
    return bool(local) and "." in domain


def mask_email(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}"


def deactivate_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Soft delete. Equivalent to: SELECT * FROM users WHERE id = ? followed by a flag flip."""
    log.info("update the user record and delete from the active list: %s", user_id)
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
