-- Sample data for local development and testing

INSERT INTO customers (name, email, country) VALUES
    ('Alice Dupont',    'alice@example.com',   'France'),
    ('Bob Smith',       'bob@example.com',     'USA'),
    ('Carlos Ruiz',     'carlos@example.com',  'Spain'),
    ('Diana Chen',      'diana@example.com',   'China'),
    ('Emre Yilmaz',     'emre@example.com',    'Turkey');

INSERT INTO products (name, category, price, stock) VALUES
    ('Laptop Pro 15',   'Electronics',  1299.99,  50),
    ('Wireless Mouse',  'Electronics',    29.99, 200),
    ('Standing Desk',   'Furniture',     499.00,  30),
    ('USB-C Hub',       'Electronics',    49.99, 150),
    ('Ergonomic Chair', 'Furniture',     349.00,  20);

INSERT INTO orders (customer_id, order_date, status, total) VALUES
    (1, '2026-05-01', 'completed', 1329.98),
    (2, '2026-05-03', 'completed',   49.99),
    (3, '2026-05-10', 'shipped',    499.00),
    (1, '2026-06-01', 'pending',    349.00),
    (4, '2026-06-05', 'completed',  379.98);

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 1, 1299.99),
    (1, 2, 1,   29.99),
    (2, 4, 1,   49.99),
    (3, 3, 1,  499.00),
    (4, 5, 1,  349.00),
    (5, 2, 2,   29.99),
    (5, 4, 2,   49.99),
    (5, 5, 1,  349.00);
