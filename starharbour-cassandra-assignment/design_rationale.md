# StarHarbour Cassandra design rationale

## 1) Query -> table mapping

| Query ID | Access pattern | Cassandra table | Partition key | Clustering | Notes |
|---|---|---|---|---|---|
| Q1 | Customer order history, newest first | `orders_by_customer_month` | `(customer_id, order_yyyymm)` | `order_ts DESC, order_id DESC` | Month bucket prevents unbounded customer partitions |
| Q2 | All line items for an order | `order_items_by_order` | `(order_id)` | `line_no ASC` | One partition per order |
| Q3 | Customer profile by id | `customers_by_id` | `(customer_id)` | none | Direct lookup |
| Q4 | Customer profile by email | `customers_by_email` | `(email)` | none | Alternate key for login |
| Q5 | Store orders on a day, newest first | `orders_by_store_day` | `(store_id, order_date)` | `order_ts DESC, order_id DESC` | Day bucket keeps partitions small |
| Q6 | Top-selling products for store month | `top_products_by_store_month` | `(store_id, sales_yyyymm)` | `rank ASC, product_id ASC` | Read-optimized leaderboard |
| Q7 | Product reviews, newest first | `reviews_by_product_month` | `(product_id, review_yyyymm)` | `review_ts DESC, review_id DESC` | Month bucket handles hot products |

## 2) Assumptions used in sizing

- Stores: 1,500
- Customers: 8,000,000
- Orders: 1,200 per store per day
- Order items: 3 per order average
- Products: ~300 active SKUs
- Reviews: long-tail; a few products can reach hundreds of thousands lifetime reviews
- Time bucketing:
  - Orders by customer: month (`yyyy-mm`)
  - Orders by store: day
  - Reviews by product: month (`yyyy-mm`)

Derived figures:

- Total orders/day = 1,500 * 1,200 = 1,800,000
- Total orders/month (~30d) = 54,000,000
- Avg orders/customer/month = 54,000,000 / 8,000,000 = 6.75

## 3) Partition-size analysis

| Table | Expected rows per partition at scale | Bounded? | Rationale |
|---|---:|---|---|
| `orders_by_customer_month` | ~7 average; heavy users maybe 100-500/month | Yes | Month bucket caps growth |
| `order_items_by_order` | ~3 rows/order | Yes | Fixed by order shape |
| `customers_by_id` | 1 | Yes | One customer row |
| `customers_by_email` | 1 | Yes | One email row |
| `orders_by_store_day` | ~1,200 rows/store/day | Yes | Day bucket by store+date |
| `top_products_by_store_month` | <=300 rows/store/month | Yes | Upper bounded by active SKU count |
| `product_sales_totals_by_store_month` | <=300 counter rows/store/month | Yes | One row per sold product |
| `reviews_by_product_month` | Product dependent; month bucket keeps rows bounded | Yes | Prevents lifetime unbounded partitions |

### Unbounded designs avoided

- `orders_by_customer(customer_id)` without bucket -> unbounded over customer lifetime.
- `orders_by_store(store_id)` without date bucket -> unbounded over store lifetime.
- `reviews_by_product(product_id)` without bucket -> can exceed hundreds of thousands rows for popular drinks.

## 4) Denormalization decisions

### Duplicated columns and why

- Customer profile duplicated in:
  - `customers_by_id`
  - `customers_by_email`
  Reason: satisfy Q3 and Q4 at read time without join/secondary index.

- Order header duplicated in:
  - `orders_by_customer_month`
  - `orders_by_store_day`
  Reason: satisfy both customer-history and store-day operational views.

- Product descriptors duplicated in `order_items_by_order` (`product_name`, `category`, `size`):
  Reason: historical receipt fidelity and read completeness without product lookup.

- Product monthly aggregates duplicated in `top_products_by_store_month`:
  Reason: direct top-N read path for Q6.

## 5) Write fan-out for new order

When an order is created (single checkout event), application writes should touch:

1. `orders_by_customer_month` (1 row)
2. `orders_by_store_day` (1 row)
3. `order_items_by_order` (N rows, N ~ 3)
4. `product_sales_totals_by_store_month` (counter increment per line item/product)
5. Optional loyalty update:
   - `customers_by_id`
   - `customers_by_email`

Then asynchronously or in a periodic job:

6. Refresh `top_products_by_store_month` rank rows for affected `(store_id, sales_yyyymm)` from totals.

## 6) Update handling from application perspective

### Customer updates

- Name/phone/loyalty changes: update both `customers_by_id` and `customers_by_email`.
- Email change:
  1. Insert/Upsert new row in `customers_by_email` using new email.
  2. Delete old email row in `customers_by_email`.
  3. Update `email` field in `customers_by_id`.

### Order updates

- Status/payment corrections: update the same order row in both:
  - `orders_by_customer_month`
  - `orders_by_store_day`

### Order item corrections

- Update row(s) in `order_items_by_order`.
- Adjust `product_sales_totals_by_store_month` counters accordingly (+/- delta).
- Recompute affected rank slice in `top_products_by_store_month`.

### Review updates/deletes

- Upsert/delete in `reviews_by_product_month` with exact primary key components:
  `(product_id, review_yyyymm, review_ts, review_id)`.

## 7) Many-to-many and aggregate note

- Relational many-to-many (`product_supplier`) is not required by Q1-Q7, so no Cassandra table is created for it in this assignment scope.
- Q6 aggregate is solved using:
  - write-optimized counters (`product_sales_totals_by_store_month`)
  - read-optimized ranked materialization (`top_products_by_store_month`).

This keeps register writes simple and top-N reads fast.
