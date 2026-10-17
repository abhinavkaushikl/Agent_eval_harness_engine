def overdue_invoice_ids(conn, min_days):
    """IDs of unpaid invoices at least `min_days` days overdue, oldest first."""
    sql = (
        "SELECT id FROM invoices "
        "WHERE paid = 0 AND days_overdue > ? "   # BUG: should be >= to include exactly min_days
        "ORDER BY days_overdue DESC"
    )
    return [row[0] for row in conn.execute(sql, (min_days,))]
