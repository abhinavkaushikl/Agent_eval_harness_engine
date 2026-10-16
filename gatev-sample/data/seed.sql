-- Seed rows. Note the DISTINGUISHING row: order 204 has a refund of exactly 5000,
-- which is the only thing that separates `refund > 5000` from `refund >= 5000`
-- (corpus A:36 — without it, a wrong boundary query passes by coincidence).
INSERT INTO customers (id, name, country) VALUES
    (1, 'Ada Lovelace',   'US'),
    (2, 'Alan Turing',    'GB'),
    (3, 'Grace Hopper',   'US'),
    (4, 'Edsger Dijkstra','NL');

INSERT INTO orders (id, customer_id, total, status, refund) VALUES
    (201, 1, 1200, 'shipped',   0),
    (202, 1,  300, 'shipped',   0),
    (203, 3, 9800, 'shipped',   0),
    (204, 3, 6000, 'cancelled', 5000),   -- distinguishing boundary row
    (205, 2,  150, 'open',      0),
    (206, 3, 7200, 'cancelled', 7200),
    (207, 4, 1050, 'shipped',   0);
