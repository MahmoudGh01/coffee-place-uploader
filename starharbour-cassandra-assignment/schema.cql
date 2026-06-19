-- StarHarbour Cassandra schema (query-first)
-- This schema is designed directly from access patterns Q1-Q7.

CREATE KEYSPACE IF NOT EXISTS starharbour
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 3
}
AND durable_writes = true;

USE starharbour;

-- Q1: Show a customer's order history, most recent first.
-- Bucket by month so customer partitions stay bounded over time.
CREATE TABLE IF NOT EXISTS orders_by_customer_month (
  customer_id uuid,
  order_yyyymm text,
  order_ts timeuuid,
  order_id uuid,
  store_id uuid,
  employee_id uuid,
  status text,
  total_amount decimal,
  payment_method text,
  PRIMARY KEY ((customer_id, order_yyyymm), order_ts, order_id)
) WITH CLUSTERING ORDER BY (order_ts DESC, order_id DESC);

-- Q2: Show all line items for a given order.
CREATE TABLE IF NOT EXISTS order_items_by_order (
  order_id uuid,
  line_no int,
  product_id uuid,
  product_name text,
  category text,
  size text,
  quantity int,
  unit_price decimal,
  line_total decimal,
  PRIMARY KEY ((order_id), line_no)
) WITH CLUSTERING ORDER BY (line_no ASC);

-- Q3: Look up customer profile by customer_id.
CREATE TABLE IF NOT EXISTS customers_by_id (
  customer_id uuid,
  full_name text,
  email text,
  phone text,
  signup_date date,
  loyalty_tier text,
  loyalty_points int,
  PRIMARY KEY ((customer_id))
);

-- Q4: Look up customer profile by email.
CREATE TABLE IF NOT EXISTS customers_by_email (
  email text,
  customer_id uuid,
  full_name text,
  phone text,
  signup_date date,
  loyalty_tier text,
  loyalty_points int,
  PRIMARY KEY ((email))
);

-- Q5: List all orders for a store on a given day, newest first.
CREATE TABLE IF NOT EXISTS orders_by_store_day (
  store_id uuid,
  order_date date,
  order_ts timeuuid,
  order_id uuid,
  customer_id uuid,
  employee_id uuid,
  status text,
  total_amount decimal,
  payment_method text,
  PRIMARY KEY ((store_id, order_date), order_ts, order_id)
) WITH CLUSTERING ORDER BY (order_ts DESC, order_id DESC);

-- Q6: Show top-selling products for a store in a given month.
-- Read-optimized rank table for direct TOP N reads.
CREATE TABLE IF NOT EXISTS top_products_by_store_month (
  store_id uuid,
  sales_yyyymm text,
  rank int,
  product_id uuid,
  product_name text,
  total_qty bigint,
  total_revenue decimal,
  PRIMARY KEY ((store_id, sales_yyyymm), rank, product_id)
) WITH CLUSTERING ORDER BY (rank ASC, product_id ASC);

-- Q6 helper: incremental quantity maintenance from checkout writes.
-- Counters are write-efficient for per-product monthly increments.
CREATE TABLE IF NOT EXISTS product_sales_totals_by_store_month (
  store_id uuid,
  sales_yyyymm text,
  product_id uuid,
  total_qty counter,
  PRIMARY KEY ((store_id, sales_yyyymm), product_id)
) WITH CLUSTERING ORDER BY (product_id ASC);

-- Q7: Show all reviews for a product, newest first.
-- Bucket by month to keep hot-product review partitions bounded.
CREATE TABLE IF NOT EXISTS reviews_by_product_month (
  product_id uuid,
  review_yyyymm text,
  review_ts timeuuid,
  review_id uuid,
  customer_id uuid,
  rating tinyint,
  comment text,
  PRIMARY KEY ((product_id, review_yyyymm), review_ts, review_id)
) WITH CLUSTERING ORDER BY (review_ts DESC, review_id DESC);
