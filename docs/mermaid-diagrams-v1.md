# Mermaid Diagrams Cho Tieu Luan - Version 1

Tai lieu nay la ban Mermaid v1 cho tieu luan AI Service ecommerce. Ban v1 dung de dua vao report va review nhanh kien truc muc tieu. Version 2 co the ve lai bang Visual Paradigm hoac draw.io de co layout dep hon cho ban nop cuoi.

Pham vi cua ban v1:

- Phan anh yeu cau PDF: ecommerce tich hop AI Service, KB_Graph Neo4j, RAG/chat, goi y trong search/cart/chat.
- Phan anh repo hien tai: `nginx` gateway, `user_service`, `product_service`, `order_service`, `payment_service`, `shipping_service`, `chatbot_service`, MySQL, PostgreSQL, Neo4j.
- Phan anh kien truc muc tieu da cat xong: Nginx la entrypoint chinh, JWT API va session UI cung ton tai, payment/shipping da tach service rieng.
- Khong thay doi logic ung dung runtime.

Ghi chu hien trang: `order_service` van giu snapshot `payment_status`, `paid_at`, `shipping_status`, va shipping address de bao toan UI/order history, nhung ban ghi payment duoc tao/cap nhat trong `payment_service` va shipment duoc tao/cap nhat trong `shipping_service`.

## 1. System Architecture Diagram

```mermaid
flowchart LR
    customer["Customer Browser"]
    staff["Staff Browser"]
    nginx["Nginx Gateway\nPrimary public entrypoint :8080"]

    subgraph docker["Docker Compose Network"]
        user["user_service\nDjango UI, Session Auth, JWT API, Staff, Gateway, Chat Proxy\nDebug ports: 8000, 8003"]
        product["product_service\nCatalog API\nDebug port: 8001"]
        order["order_service\nCart, Saved, Compare, Order Orchestration\nCurrent internal-only"]
        payment["payment_service\nPayment records and confirmation\nInternal-only"]
        shipping["shipping_service\nShipment records and status lifecycle\nInternal-only"]
        chatbot["chatbot_service\nAI Chat, RAG, Behavior Ingest\nDebug port: 8005"]

        mysql_user[("MySQL\nuser_db")]
        mysql_order[("MySQL\norder_db")]
        pg_product[("PostgreSQL\nproduct_db")]
        pg_payment[("PostgreSQL\npayment_db")]
        pg_shipping[("PostgreSQL\nshipping_db")]
        pg_chatbot[("PostgreSQL\nchatbot_db")]
        neo4j[("Neo4j\nBehavior KB Graph")]
        artifacts[("File artifacts\nchatbot/artifacts")]
    end

    customer --> nginx
    staff --> nginx
    nginx -->|"UI routes /customer, /staff, /gateway\nAuth API /api/auth"| user
    nginx -->|"Catalog API /api/products"| product
    nginx -->|"Chat API /api/chat"| chatbot

    user -->|"Session/JWT auth + local editorial"| mysql_user
    user -->|"Catalog reads and staff writes"| product
    user -->|"Cart, checkout, orders\nX-Internal-Key"| order
    user -->|"Chat proxy\n/customer/chatbot/reply"| chatbot

    product --> pg_product
    order --> mysql_order
    order -->|"Create/confirm payment records"| payment
    order -->|"Create/update shipment records"| shipping
    payment --> pg_payment
    shipping --> pg_shipping

    chatbot -->|"Product context"| product
    chatbot -->|"BehaviorEvent"| pg_chatbot
    chatbot -->|"Graph retrieval/import"| neo4j
    chatbot -->|"KB, model_best, metrics, dataset"| artifacts
```

## 2. DDD Context Map

```mermaid
flowchart TB
    subgraph identity["Identity and UI Context - user_service"]
        auth["Auth source\nDjango User, customer, staff"]
        ui["Customer/staff web UI"]
        gateway["Gateway/orchestrator helpers"]
        editorial["BlogPost, Testimonial"]
    end

    subgraph catalog["Catalog Context - product_service"]
        category["Category"]
        product["Product"]
        staffWrite["Staff protected catalog writes\nX-Staff-Key"]
    end

    subgraph commerce["Commerce Context - order_service"]
        cart["CartItem"]
        saved["SavedItem"]
        compare["CompareItem"]
        order["Order and OrderItem"]
        orderShipping["Payment/shipping snapshots\nfor existing UI"]
        behaviorSource["Behavior source export"]
    end

    subgraph payment["Payment Context - payment_service"]
        paymentCommand["Authorize/capture payment"]
        paymentRecord["PaymentTransaction"]
    end

    subgraph shipping["Shipping Context - shipping_service"]
        shipmentCommand["Create/update shipment"]
        shipmentRecord["Shipment"]
    end

    subgraph ai["AI Assistant Context - chatbot_service"]
        behaviorEvent["BehaviorEvent"]
        behaviorModel["RNN/LSTM/BiLSTM\nmodel_best"]
        rag["File RAG knowledge base"]
        kbgraph["Neo4j KB_Graph"]
        chat["Chat reply and recommendations"]
    end

    auth -->|"Authenticated user_id"| ui
    ui -->|"Open Host Service\ncatalog read/write via API"| catalog
    ui -->|"Customer/Supplier\ncart, checkout, orders"| commerce
    commerce -->|"Catalog snapshot by id/category"| catalog
    commerce -->|"Internal API\npayment requested/paid"| payment
    commerce -->|"Internal API\nshipment requested/status changed"| shipping
    commerce -->|"Behavior records for AI recovery"| ai
    ai -->|"Catalog lookup and recommendation candidates"| catalog
    ai -->|"Behavior graph context"| kbgraph
    kbgraph --> ai
```

## 3. Class Diagram

```mermaid
classDiagram
    class User {
        +int id
        +string username
        +string email
        +bool is_staff
        +bool is_superuser
    }

    class BlogPost {
        +string title
        +string slug
        +string category
        +string author
        +text excerpt
        +text body
        +date published_at
    }

    class Testimonial {
        +string name
        +string role
        +int rating
        +text quote
        +bool is_featured
    }

    class LegacyUserMapping {
        +string legacy_source
        +int legacy_user_id
        +string legacy_username
        +string legacy_email
    }

    class Category {
        +int id
        +string name
        +string slug
        +text description
        +string hero_image_url
        +int sort_order
        +bool is_active
    }

    class Product {
        +int id
        +string name
        +string brand
        +text description
        +string image_url
        +decimal price
        +int stock
    }

    class ProductSnapshotMixin {
        <<abstract>>
        +string category_slug
        +string category_name
        +int product_id
        +string product_name
        +string product_brand
        +string product_image_url
        +decimal unit_price
    }

    class CartItem {
        +int user_id
        +int quantity
        +datetime created_at
        +datetime updated_at
        +total_price()
    }

    class SavedItem {
        +int user_id
        +datetime created_at
    }

    class CompareItem {
        +int user_id
        +int stock
        +datetime created_at
    }

    class Order {
        +int user_id
        +decimal total_amount
        +string payment_status
        +string shipping_status
        +string source
        +int source_order_id
        +datetime paid_at
        +can_pay()
        +can_update_shipping_status()
    }

    class OrderItem {
        +int quantity
        +total_price()
    }

    class OrderShipping {
        +string recipient_name
        +string phone
        +string address_line
        +string city_or_region
        +string postal_code
        +string country
        +text note
    }

    class PaymentTransaction {
        <<payment_service>>
        +int order_id
        +int user_id
        +decimal amount
        +string provider
        +string status
        +datetime paid_at
    }

    class Shipment {
        <<shipping_service>>
        +int order_id
        +string status
        +string recipient_name
        +string phone
        +string address_line
        +datetime updated_at
    }

    class BehaviorEvent {
        +string user_ref
        +string event_type
        +string category_slug
        +int product_id
        +json metadata
        +datetime created_at
    }

    class GraphUser {
        <<Neo4j>>
        +string user_ref
        +int event_count
        +string primary_category_slug
        +float affinity_total
    }

    class GraphBehavior {
        <<Neo4j>>
        +string behavior_id
        +string behavior_type
        +string event_ts
        +string session_id
        +float affinity_weight
    }

    class GraphCategory {
        <<Neo4j>>
        +string slug
        +string name
    }

    class GraphProduct {
        <<Neo4j>>
        +int product_id
        +string name
        +string brand
        +float price
        +int stock
    }

    User "1" --> "*" LegacyUserMapping
    Category "1" --> "*" Product
    ProductSnapshotMixin <|-- CartItem
    ProductSnapshotMixin <|-- SavedItem
    ProductSnapshotMixin <|-- CompareItem
    ProductSnapshotMixin <|-- OrderItem
    Order "1" --> "*" OrderItem
    Order "1" --> "1" OrderShipping
    Order "1" --> "0..*" PaymentTransaction
    Order "1" --> "0..1" Shipment
    User "1" ..> "*" CartItem : user_id
    User "1" ..> "*" SavedItem : user_id
    User "1" ..> "*" CompareItem : user_id
    User "1" ..> "*" Order : user_id
    BehaviorEvent ..> User : user_ref
    BehaviorEvent ..> Product : category_slug/product_id
    GraphUser "1" --> "*" GraphBehavior : PERFORMED
    GraphBehavior "*" --> "1" GraphCategory : IN_CATEGORY
    GraphBehavior "*" --> "0..1" GraphProduct : ON_PRODUCT
    GraphProduct "*" --> "1" GraphCategory : BELONGS_TO
    GraphUser "*" --> "*" GraphCategory : PREFERS
```

## 4. Sequence Diagram - Flow Mua Hang

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant N as Nginx Gateway
    participant U as user_service
    participant P as product_service
    participant O as order_service
    participant Pay as payment_service
    participant Ship as shipping_service
    participant Bot as chatbot_service
    participant G as Neo4j KB_Graph

    C->>N: Open /customer/dashboard
    N->>U: Route customer UI request
    U->>P: GET /api/categories and /api/products
    P-->>U: Category and product list
    U-->>C: Render dashboard with products

    opt AI search suggestions
        U->>Bot: POST /api/chat/reply with user_context and search intent
        Bot->>P: GET product candidates
        Bot->>G: Query behavior graph context
        G-->>Bot: Preference/category/product context
        Bot-->>U: Answer, recommendations, citations
        U-->>C: Render "AI goi y cho ban"
    end

    C->>N: Add product to cart
    N->>U: POST /customer/cart/add
    U->>O: POST /api/cart with product snapshot and user_id
    O-->>U: Cart item saved
    U-->>C: Redirect dashboard/cart

    C->>N: Open cart
    N->>U: GET /customer/cart
    U->>O: GET /api/cart?user_id
    O-->>U: Cart items
    U->>Bot: POST /api/chat/reply for buy-together recommendations
    Bot->>P: GET product candidates
    Bot-->>U: Cart recommendations
    U-->>C: Render cart and AI recommendations

    C->>N: Submit checkout form
    N->>U: POST /customer/checkout
    U->>O: POST /api/checkout with shipping data
    O->>O: Create Order, OrderItem snapshots
    O->>Pay: Create payment intent
    Pay-->>O: Payment pending/authorized
    O->>Ship: Create shipment request
    Ship-->>O: Shipment pending
    O-->>U: Order created
    U-->>C: Show order with pending payment/shipping

    C->>N: Pay order
    N->>U: POST /customer/orders/{id}/pay
    U->>O: POST /api/orders/{id}/pay
    O->>Pay: Capture payment
    Pay-->>O: Payment paid
    O-->>U: Order payment_status paid
    U-->>C: Payment success message

    U->>Bot: Optional ingest/backfill behavior from order history
    Bot->>G: Import/update behavior graph for RAG context
```

## 5. Database Mapping Theo Tung Service

### 5.1 Mapping Summary

| Service | Database | Runtime status | Main ownership |
|---|---|---|---|
| `user_service` | MySQL `user_db` | Current | Django auth user, customer/staff UI state, editorial content, legacy user mapping |
| `product_service` | PostgreSQL `product_db` | Current | Category and Product catalog |
| `order_service` | MySQL `order_db` | Current | Cart, saved, compare, order, order item snapshots, current payment/shipping statuses |
| `payment_service` | PostgreSQL `payment_db` | Current | Payment transaction and provider status; `order_service` keeps payment snapshots for UI compatibility |
| `shipping_service` | PostgreSQL `shipping_db` | Current | Shipment address/status lifecycle; `order_service` keeps shipping snapshots for UI compatibility |
| `chatbot_service` | PostgreSQL `chatbot_db` | Current | BehaviorEvent persistence |
| `chatbot_service` | Neo4j `neo4j` | Current optional | User/Behavior/Category/Product graph for KB_Graph and RAG context |
| `chatbot_service` | File artifacts | Current | `data_user500.csv`, sample 20 rows, metrics, model_best, RAG KB JSON, graph SVG |

### 5.2 user_service - MySQL user_db

```mermaid
erDiagram
    AUTH_USER {
        int id PK
        string username
        string email
        bool is_staff
        bool is_superuser
    }

    CUSTOMER_BLOGPOST {
        int id PK
        string title
        string slug UK
        string category
        string author
        text excerpt
        text body
        date published_at
    }

    CUSTOMER_TESTIMONIAL {
        int id PK
        string name
        string role
        int rating
        text quote
        bool is_featured
    }

    CUSTOMER_LEGACYUSERMAPPING {
        int id PK
        int user_id FK
        string legacy_source
        int legacy_user_id
        string legacy_username
        string legacy_email
    }

    AUTH_USER ||--o{ CUSTOMER_LEGACYUSERMAPPING : maps
```

### 5.3 product_service - PostgreSQL product_db

```mermaid
erDiagram
    CATALOG_CATEGORY {
        int id PK
        string name UK
        string slug UK
        text description
        string hero_image_url
        int sort_order
        bool is_active
    }

    CATALOG_PRODUCT {
        int id PK
        int category_id FK
        string name
        string brand
        text description
        string image_url
        decimal price
        int stock
        datetime created_at
        datetime updated_at
    }

    CATALOG_CATEGORY ||--o{ CATALOG_PRODUCT : contains
```

### 5.4 order_service - MySQL order_db

```mermaid
erDiagram
    ORDERS_CARTITEM {
        int id PK
        int user_id
        string category_slug
        string category_name
        int product_id
        string product_name
        string product_brand
        decimal unit_price
        int quantity
    }

    ORDERS_SAVEDITEM {
        int id PK
        int user_id
        string category_slug
        int product_id
        string product_name
        decimal unit_price
    }

    ORDERS_COMPAREITEM {
        int id PK
        int user_id
        string category_slug
        int product_id
        string product_name
        decimal unit_price
        int stock
    }

    ORDERS_ORDER {
        int id PK
        int user_id
        decimal total_amount
        string payment_status
        string shipping_status
        string source
        int source_order_id
        datetime paid_at
        datetime created_at
    }

    ORDERS_ORDERITEM {
        int id PK
        int order_id FK
        string category_slug
        string category_name
        int product_id
        string product_name
        string product_brand
        decimal unit_price
        int quantity
    }

    ORDERS_ORDERSHIPPING {
        int id PK
        int order_id FK
        string recipient_name
        string phone
        string address_line
        string city_or_region
        string postal_code
        string country
        text note
    }

    ORDERS_ORDER ||--o{ ORDERS_ORDERITEM : has
    ORDERS_ORDER ||--|| ORDERS_ORDERSHIPPING : ships_to
```

### 5.5 payment_service - PostgreSQL payment_db

```mermaid
erDiagram
    PAYMENT_TRANSACTION {
        int id PK
        int order_id
        int user_id
        decimal amount
        string currency
        string provider
        string provider_reference
        string status
        datetime authorized_at
        datetime captured_at
        datetime created_at
    }

    PAYMENT_EVENT {
        int id PK
        int transaction_id FK
        string event_type
        json payload
        datetime created_at
    }

    PAYMENT_TRANSACTION ||--o{ PAYMENT_EVENT : records
```

### 5.6 shipping_service - PostgreSQL shipping_db

```mermaid
erDiagram
    SHIPMENT {
        int id PK
        int order_id
        int user_id
        string status
        string recipient_name
        string phone
        string address_line
        string city_or_region
        string postal_code
        string country
        datetime created_at
        datetime updated_at
    }

    SHIPMENT_EVENT {
        int id PK
        int shipment_id FK
        string status
        string note
        datetime created_at
    }

    SHIPMENT ||--o{ SHIPMENT_EVENT : tracks
```

### 5.7 chatbot_service - PostgreSQL chatbot_db va Neo4j KB_Graph

```mermaid
erDiagram
    CHATBOT_BEHAVIOREVENT {
        int id PK
        string user_ref
        string event_type
        string category_slug
        int product_id
        json metadata
        datetime created_at
    }
```

```mermaid
flowchart LR
    gu["Neo4j User\nuser_ref, event_count, primary_category_slug"]
    gb["Neo4j Behavior\nbehavior_id, behavior_type, session_id, affinity_weight"]
    gc["Neo4j Category\nslug, name"]
    gp["Neo4j Product\nproduct_id, name, brand, price, stock"]

    gu -->|"PERFORMED"| gb
    gb -->|"IN_CATEGORY"| gc
    gb -->|"ON_PRODUCT"| gp
    gp -->|"BELONGS_TO"| gc
    gu -->|"PREFERS\nscore, share, rank"| gc
```

### 5.8 Runtime Data Flow Mapping

```mermaid
flowchart TD
    auth["user_service MySQL\nAuth, LegacyUserMapping, BlogPost, Testimonial"]
    catalog["product_service PostgreSQL\nCategory, Product"]
    orders["order_service MySQL\nCart/Saved/Compare/Order snapshots"]
    payment["payment_service PostgreSQL\nPaymentTransaction"]
    shipping["shipping_service PostgreSQL\nShipment"]
    behavior["chatbot_service PostgreSQL\nBehaviorEvent"]
    graphDb["Neo4j\nUser-Behavior-Category-Product graph"]
    files["chatbot artifacts\nCSV, model_best, KB JSON, metrics"]

    auth -->|"user_id identity"| orders
    catalog -->|"product snapshot copied at cart/order time"| orders
    orders -->|"payment command/status sync"| payment
    orders -->|"shipment command/status sync"| shipping
    orders -->|"behavior-source/backfill records"| behavior
    behavior -->|"graph import and preference aggregation"| graphDb
    catalog -->|"build_chat_kb and live product lookup"| files
    files -->|"RAG context and model_best"| behavior
    graphDb -->|"behavior context"| behavior
```
