-- The support-copilot order database (SQLite dialect).
CREATE TABLE customers (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    country TEXT NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    total       INTEGER NOT NULL,   -- order total, in whole currency units
    status      TEXT NOT NULL,      -- 'shipped' | 'open' | 'cancelled'
    refund      INTEGER NOT NULL    -- amount refunded, 0 when none
);
