# ER Diagram: StockFlow

This diagram is written in Mermaid. To see it as a picture:
- in VS Code, install the extension **"Markdown Preview Mermaid Support"**, then open this file and press `Ctrl+Shift+V`
- or paste the code block into https://mermaid.live

For the report you can also draw it in MySQL Workbench: **Database > Reverse Engineer**, pick `stockflow`, and Workbench draws all tables and links for you.

```mermaid
erDiagram
    categories ||--o{ products : "groups"
    suppliers |o--o{ products : "default supplier of"
    products ||--o{ stock_levels : "stocked as"
    warehouses ||--o{ stock_levels : "holds"
    suppliers ||--o{ purchase_orders : "receives"
    warehouses ||--o{ purchase_orders : "delivered to"
    purchase_orders ||--|{ purchase_order_items : "contains"
    products ||--o{ purchase_order_items : "bought in"
    customers ||--o{ customer_orders : "places"
    warehouses ||--o{ customer_orders : "ships"
    customer_orders ||--|{ order_items : "contains"
    products ||--o{ order_items : "sold in"
    products ||--o{ stock_movements : "moved"
    warehouses ||--o{ stock_movements : "at"
    app_users ||--o{ stock_movements : "performed by"
    app_users ||--o{ customer_orders : "created by"
    app_users ||--o{ purchase_orders : "created by"
    products ||--o{ reorder_alerts : "alerted"
    warehouses ||--o{ reorder_alerts : "at"

    categories { int category_id PK
                 varchar name UK
                 varchar description }
    suppliers { int supplier_id PK
                varchar name
                varchar contact_person
                varchar email UK
                varchar phone
                varchar city
                bool is_active }
    warehouses { int warehouse_id PK
                 varchar name UK
                 varchar city }
    products { int product_id PK
               varchar sku UK
               varchar name
               int category_id FK
               int default_supplier_id FK
               decimal unit_price
               decimal cost_price
               int reorder_level
               bool is_active }
    customers { int customer_id PK
                varchar name
                varchar email UK
                varchar phone
                varchar city }
    app_users { int user_id PK
                varchar username UK
                varchar password_hash
                enum role
                bool is_active }
    stock_levels { int product_id PK,FK
                   int warehouse_id PK,FK
                   int quantity_on_hand
                   int quantity_reserved }
    purchase_orders { int po_id PK
                      int supplier_id FK
                      int warehouse_id FK
                      enum status
                      datetime order_date
                      datetime received_date
                      int created_by FK }
    purchase_order_items { int po_id PK,FK
                           int product_id PK,FK
                           int quantity
                           decimal unit_cost }
    customer_orders { int order_id PK
                      int customer_id FK
                      int warehouse_id FK
                      enum status
                      datetime order_date
                      datetime shipped_date
                      int created_by FK }
    order_items { int order_id PK,FK
                  int product_id PK,FK
                  int quantity
                  decimal unit_price }
    stock_movements { bigint movement_id PK
                      int product_id FK
                      int warehouse_id FK
                      int change_qty
                      enum movement_type
                      enum reference_type
                      int reference_id
                      int performed_by FK
                      varchar note
                      datetime created_at }
    reorder_alerts { int alert_id PK
                     int product_id FK
                     int warehouse_id FK
                     int available_at_alert
                     int reorder_level_at_alert
                     enum status
                     datetime created_at
                     datetime resolved_at }
```

## Relationships in words

| Relationship | Type | How it is stored |
|---|---|---|
| A category has many products | 1 to many | `products.category_id` |
| A supplier is the default supplier of many products (optional) | 0/1 to many | `products.default_supplier_id` (NULL allowed) |
| Products and warehouses | many to many | junction table `stock_levels` (one row per pair) |
| Purchase orders and products | many to many | junction table `purchase_order_items` |
| Customer orders and products | many to many | junction table `order_items` |
| Every stock change | many per product per warehouse | `stock_movements` (the ledger) |
