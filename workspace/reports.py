"""Customer reports — fetches data from app.db."""
import sqlite3

US_CUSTOMERS = "SELECT id, name FROM customers WHERE country = 'US'"
TOP_BALANCES = "SELECT name, balance FROM customers ORDER BY balance DESC"

def us_customers(conn):
    return conn.execute(US_CUSTOMERS).fetchall()

def top_balances(conn):
    return conn.execute(TOP_BALANCES).fetchall()

def vip(conn):
    # BUG: there is no 'tier' column in customers
    return conn.execute("SELECT name FROM customers WHERE tier = 'gold'").fetchall()

def reset_balance(conn, cid):
    # BUG: a data-FETCH module should never write
    conn.execute("UPDATE customers SET balance = 0 WHERE id = ?", (cid,))
