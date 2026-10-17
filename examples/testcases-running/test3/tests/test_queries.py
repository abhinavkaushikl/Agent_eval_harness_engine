import sqlite3

import pytest

from queries import overdue_invoice_ids


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE invoices (id INTEGER, paid INTEGER, days_overdue INTEGER)")
    c.executemany(
        "INSERT INTO invoices VALUES (?, ?, ?)",
        [(1, 0, 90), (2, 0, 30), (3, 1, 120), (4, 0, 30)],  # 3 is paid; 2 and 4 are exactly 30
    )
    return c


def test_strictly_overdue(conn):
    assert overdue_invoice_ids(conn, 60) == [1]


def test_boundary_is_inclusive(conn):
    # invoices exactly 30 days overdue must be included at min_days=30
    assert overdue_invoice_ids(conn, 30) == [1, 2, 4]


def test_paid_invoices_excluded(conn):
    assert 3 not in overdue_invoice_ids(conn, 0)
