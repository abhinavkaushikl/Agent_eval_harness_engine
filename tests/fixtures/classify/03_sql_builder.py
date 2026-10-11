# expect: sql_generation -- the one function builds and executes a SELECT; its correctness is the query's result set (A1 via a database).
import sqlite3


def overdue_invoices(conn: sqlite3.Connection, days: int) -> list[tuple[int, str, float]]:
    query = (
        "SELECT id, customer, amount FROM invoices "
        "WHERE paid = 0 AND julianday('now') - julianday(issued) > ? "
        "ORDER BY issued"
    )
    return conn.execute(query, (days,)).fetchall()
