-- Synthetic seed data for the sample e-commerce schema.
-- Small but rich enough for JOINs, GROUP BY aggregation, and date filtering.

INSERT INTO customers (customer_id, full_name, email, country, created_at) VALUES
    (1, 'Alice Johnson',  'alice@example.com',  'USA',     '2025-01-12'),
    (2, 'Bruno Costa',    'bruno@example.com',  'Brazil',  '2025-02-03'),
    (3, 'Chen Wei',       'chen@example.com',   'China',   '2025-02-20'),
    (4, 'Deniz Yilmaz',   'deniz@example.com',  'Turkey',  '2025-03-15'),
    (5, 'Emma Schmidt',   'emma@example.com',   'Germany', '2025-04-01'),
    (6, 'Farah Haddad',   'farah@example.com',  'UAE',     '2025-05-09');

INSERT INTO products (product_id, name, category, unit_price) VALUES
    (1, 'Wireless Mouse',        'Electronics', 24.99),
    (2, 'Mechanical Keyboard',   'Electronics', 89.50),
    (3, '27-inch Monitor',       'Electronics', 219.00),
    (4, 'USB-C Hub',             'Accessories', 39.90),
    (5, 'Laptop Stand',          'Accessories', 32.00),
    (6, 'Noise-Cancel Headset',  'Audio',       149.99),
    (7, 'Webcam 1080p',          'Electronics', 59.00),
    (8, 'Desk Lamp',             'Home Office', 27.50);

INSERT INTO orders (order_id, customer_id, status, ordered_at) VALUES
    (1,  1, 'delivered', '2025-03-01'),
    (2,  1, 'delivered', '2025-04-18'),
    (3,  2, 'shipped',   '2025-04-22'),
    (4,  3, 'delivered', '2025-05-02'),
    (5,  3, 'cancelled', '2025-05-05'),
    (6,  4, 'delivered', '2025-05-20'),
    (7,  5, 'shipped',   '2025-06-01'),
    (8,  5, 'pending',   '2025-06-10'),
    (9,  6, 'delivered', '2025-06-15'),
    (10, 2, 'delivered', '2025-06-28');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1,  1, 2, 24.99),
    (1,  4, 1, 39.90),
    (2,  3, 1, 219.00),
    (2,  6, 1, 149.99),
    (3,  2, 1, 89.50),
    (3,  5, 2, 32.00),
    (4,  7, 3, 59.00),
    (4,  1, 1, 24.99),
    (5,  3, 1, 219.00),
    (6,  6, 2, 149.99),
    (6,  8, 1, 27.50),
    (7,  2, 1, 89.50),
    (7,  4, 2, 39.90),
    (8,  5, 1, 32.00),
    (9,  3, 2, 219.00),
    (9,  7, 1, 59.00),
    (10, 1, 4, 24.99),
    (10, 8, 2, 27.50);

-- Keep SERIAL sequences in sync after explicit-id inserts so future inserts
-- (if any) do not collide with the seeded primary keys.
SELECT setval('customers_customer_id_seq',     (SELECT MAX(customer_id) FROM customers));
SELECT setval('products_product_id_seq',       (SELECT MAX(product_id) FROM products));
SELECT setval('orders_order_id_seq',           (SELECT MAX(order_id) FROM orders));
SELECT setval('order_items_order_item_id_seq', (SELECT MAX(order_item_id) FROM order_items));
