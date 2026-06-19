# StarHarbour Cassandra Assignment

This module contains the assignment deliverables:

- `schema.cql`
- `design_rationale.md`
- `sample_data.cql`

## Run locally with Docker Compose

If you use a 3-node Cassandra Docker Compose setup, start it first:

```bash
docker compose up -d
```

Verify nodes are up:

```bash
docker exec -it cassandra-1 nodetool status
```

You should see all three nodes as `UN`.

## Apply schema

From this module directory, run:

```bash
docker exec -i cassandra-1 cqlsh < schema.cql
```

## Load sample data

```bash
docker exec -i cassandra-1 cqlsh < sample_data.cql
```

## Query examples for Q1-Q7

Use:

```bash
docker exec -it cassandra-1 cqlsh
```

Then:

```sql
USE starharbour;
```

### Q1: Customer order history (newest first)

```sql
SELECT order_ts, order_id, store_id, status, total_amount, payment_method
FROM orders_by_customer_month
WHERE customer_id = 11111111-1111-1111-1111-111111111111
  AND order_yyyymm = '2026-06'
LIMIT 50;
```

### Q2: Line items for one order

```sql
SELECT line_no, product_id, product_name, quantity, unit_price, line_total
FROM order_items_by_order
WHERE order_id = 22222222-2222-2222-2222-222222222222;
```

### Q3: Customer profile by `customer_id`

```sql
SELECT customer_id, full_name, email, phone, signup_date, loyalty_tier, loyalty_points
FROM customers_by_id
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

### Q4: Customer profile by `email`

```sql
SELECT email, customer_id, full_name, phone, signup_date, loyalty_tier, loyalty_points
FROM customers_by_email
WHERE email = 'alex@example.com';
```

### Q5: Store orders for a day (newest first)

```sql
SELECT order_ts, order_id, customer_id, employee_id, status, total_amount, payment_method
FROM orders_by_store_day
WHERE store_id = 33333333-3333-3333-3333-333333333333
  AND order_date = '2026-06-19'
LIMIT 100;
```

### Q6: Top-selling products for store-month

```sql
SELECT rank, product_id, product_name, total_qty, total_revenue
FROM top_products_by_store_month
WHERE store_id = 33333333-3333-3333-3333-333333333333
  AND sales_yyyymm = '2026-06'
LIMIT 10;
```

### Q7: Product reviews (newest first)

```sql
SELECT review_ts, review_id, customer_id, rating, comment
FROM reviews_by_product_month
WHERE product_id = 44444444-4444-4444-4444-444444444444
  AND review_yyyymm = '2026-06'
LIMIT 100;
```

## Suggested smoke test flow

1. Apply `schema.cql`.
2. Apply `sample_data.cql`.
3. Run Q1-Q7 queries from this README.
4. Verify ordering:
   - Q1 and Q5 newest first.
   - Q2 by ascending `line_no`.
   - Q7 newest first.
