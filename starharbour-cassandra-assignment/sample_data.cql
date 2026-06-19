-- Sample data for StarHarbour Cassandra assignment
-- Apply after schema.cql

USE starharbour;

-- Fixed IDs used in README query examples
-- customer_id: 11111111-1111-1111-1111-111111111111
-- order_id:    22222222-2222-2222-2222-222222222222
-- store_id:    33333333-3333-3333-3333-333333333333
-- product_id:  44444444-4444-4444-4444-444444444444

-- Q3 / Q4: customer profile by id and by email
INSERT INTO customers_by_id (
  customer_id, full_name, email, phone, signup_date, loyalty_tier, loyalty_points
) VALUES (
  11111111-1111-1111-1111-111111111111,
  'Alex Carter',
  'alex@example.com',
  '+1-555-0101',
  '2025-01-10',
  'gold',
  1280
);

INSERT INTO customers_by_email (
  email, customer_id, full_name, phone, signup_date, loyalty_tier, loyalty_points
) VALUES (
  'alex@example.com',
  11111111-1111-1111-1111-111111111111,
  'Alex Carter',
  '+1-555-0101',
  '2025-01-10',
  'gold',
  1280
);

-- Q1: customer order history (same customer, two orders in same month)
INSERT INTO orders_by_customer_month (
  customer_id, order_yyyymm, order_ts, order_id, store_id, employee_id, status, total_amount, payment_method
) VALUES (
  11111111-1111-1111-1111-111111111111,
  '2026-06',
  0f4c3f10-58cc-11ef-8c99-0242ac120002,
  22222222-2222-2222-2222-222222222222,
  33333333-3333-3333-3333-333333333333,
  77777777-7777-7777-7777-777777777777,
  'PAID',
  14.40,
  'CARD'
);

INSERT INTO orders_by_customer_month (
  customer_id, order_yyyymm, order_ts, order_id, store_id, employee_id, status, total_amount, payment_method
) VALUES (
  11111111-1111-1111-1111-111111111111,
  '2026-06',
  1a6d5010-58cc-11ef-8c99-0242ac120002,
  aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
  33333333-3333-3333-3333-333333333333,
  88888888-8888-8888-8888-888888888888,
  'PAID',
  9.20,
  'WALLET'
);

-- Q5: store-day orders (same two orders, newest first by order_ts)
INSERT INTO orders_by_store_day (
  store_id, order_date, order_ts, order_id, customer_id, employee_id, status, total_amount, payment_method
) VALUES (
  33333333-3333-3333-3333-333333333333,
  '2026-06-19',
  0f4c3f10-58cc-11ef-8c99-0242ac120002,
  22222222-2222-2222-2222-222222222222,
  11111111-1111-1111-1111-111111111111,
  77777777-7777-7777-7777-777777777777,
  'PAID',
  14.40,
  'CARD'
);

INSERT INTO orders_by_store_day (
  store_id, order_date, order_ts, order_id, customer_id, employee_id, status, total_amount, payment_method
) VALUES (
  33333333-3333-3333-3333-333333333333,
  '2026-06-19',
  1a6d5010-58cc-11ef-8c99-0242ac120002,
  aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
  11111111-1111-1111-1111-111111111111,
  88888888-8888-8888-8888-888888888888,
  'PAID',
  9.20,
  'WALLET'
);

-- Q2: line items for one order
INSERT INTO order_items_by_order (
  order_id, line_no, product_id, product_name, category, size, quantity, unit_price, line_total
) VALUES (
  22222222-2222-2222-2222-222222222222,
  1,
  44444444-4444-4444-4444-444444444444,
  'Caramel Latte',
  'espresso',
  'medium',
  1,
  5.20,
  5.20
);

INSERT INTO order_items_by_order (
  order_id, line_no, product_id, product_name, category, size, quantity, unit_price, line_total
) VALUES (
  22222222-2222-2222-2222-222222222222,
  2,
  66666666-6666-4666-8666-666666666666,
  'Blueberry Muffin',
  'bakery',
  'single',
  1,
  3.10,
  3.10
);

INSERT INTO order_items_by_order (
  order_id, line_no, product_id, product_name, category, size, quantity, unit_price, line_total
) VALUES (
  22222222-2222-2222-2222-222222222222,
  3,
  99999999-9999-4999-8999-999999999999,
  'Cold Brew',
  'coffee',
  'large',
  1,
  6.10,
  6.10
);

-- Q6: top-selling products for store-month
INSERT INTO top_products_by_store_month (
  store_id, sales_yyyymm, rank, product_id, product_name, total_qty, total_revenue
) VALUES (
  33333333-3333-3333-3333-333333333333,
  '2026-06',
  1,
  44444444-4444-4444-4444-444444444444,
  'Caramel Latte',
  120,
  624.00
);

INSERT INTO top_products_by_store_month (
  store_id, sales_yyyymm, rank, product_id, product_name, total_qty, total_revenue
) VALUES (
  33333333-3333-3333-3333-333333333333,
  '2026-06',
  2,
  99999999-9999-4999-8999-999999999999,
  'Cold Brew',
  95,
  579.50
);

INSERT INTO top_products_by_store_month (
  store_id, sales_yyyymm, rank, product_id, product_name, total_qty, total_revenue
) VALUES (
  33333333-3333-3333-3333-333333333333,
  '2026-06',
  3,
  66666666-6666-4666-8666-666666666666,
  'Blueberry Muffin',
  80,
  248.00
);

-- Q6 helper counters
UPDATE product_sales_totals_by_store_month
SET total_qty = total_qty + 120
WHERE store_id = 33333333-3333-3333-3333-333333333333
  AND sales_yyyymm = '2026-06'
  AND product_id = 44444444-4444-4444-4444-444444444444;

UPDATE product_sales_totals_by_store_month
SET total_qty = total_qty + 95
WHERE store_id = 33333333-3333-3333-3333-333333333333
  AND sales_yyyymm = '2026-06'
  AND product_id = 99999999-9999-4999-8999-999999999999;

UPDATE product_sales_totals_by_store_month
SET total_qty = total_qty + 80
WHERE store_id = 33333333-3333-3333-3333-333333333333
  AND sales_yyyymm = '2026-06'
  AND product_id = 66666666-6666-4666-8666-666666666666;

-- Q7: reviews newest first in month bucket
INSERT INTO reviews_by_product_month (
  product_id, review_yyyymm, review_ts, review_id, customer_id, rating, comment
) VALUES (
  44444444-4444-4444-4444-444444444444,
  '2026-06',
  2b7f6110-58cc-11ef-8c99-0242ac120002,
  55555555-5555-4555-8555-555555555555,
  11111111-1111-1111-1111-111111111111,
  5,
  'Great balance of sweetness and espresso.'
);

INSERT INTO reviews_by_product_month (
  product_id, review_yyyymm, review_ts, review_id, customer_id, rating, comment
) VALUES (
  44444444-4444-4444-4444-444444444444,
  '2026-06',
  3c8a7210-58cc-11ef-8c99-0242ac120002,
  bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
  cccccccc-cccc-4ccc-8ccc-cccccccccccc,
  4,
  'Tasty, but a little too sweet for me.'
);
