-- Sample schema with planted modeling problems.

CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone1 TEXT,
    phone2 TEXT,
    phone3 TEXT
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    total NUMERIC NOT NULL
);

CREATE TABLE order_events (
    order_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    happened_at TEXT NOT NULL
);

CREATE INDEX idx_order_events_order ON order_events (order_id);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
