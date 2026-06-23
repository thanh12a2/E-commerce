# 📊 HƯỚNG DẪN ER DIAGRAM - SCHEMA CƠ SỞ DỮ LIỆU CHUNG

**File**: [ER-DIAGRAM-COMPLETE.puml](ER-DIAGRAM-COMPLETE.puml)

---

## 1. CÁCH ĐỌC ER DIAGRAM

### 1.1 Ký Hiệu & Quy Ước

```
┌─────────────────┐
│ TableName       │
├─────────────────┤
│ * id : Type     │ ← * = Primary Key (PK)
│ * field : Type  │ ← Không thể NULL
│   field : Type  │ ← Có thể NULL
│ : Constraint    │ ← UNIQUE, <<FK>>, v.v.
└─────────────────┘
```

### 1.2 Các Loại Mối Quan Hệ

| Ký Hiệu | Mô Tả | Ví Dụ |
|---------|-------|-------|
| `"1" --> "1"` | One-to-One | 1 User ↔ 1 Cart |
| `"1" --> "N"` | One-to-Many | 1 User → N Orders |
| `"N" --> "M"` | Many-to-Many | (cần junction table) |

### 1.3 Color Code (Màu Sắc Theo Dịch Vụ)

- 🟨 **MYSQL** (Vàng): user_service, order_service
- 🟦 **PostgreSQL** (Xanh): product_service, payment_service, shipping_service, chatbot_service
- 🟩 **Neo4j** (Xanh lá): Optional behavior graph

---

## 2. SCHEMA CƠ SỞ DỮ LIỆU CHI TIẾT

### 2.1 MYSQL - USER SERVICE (user_db)

#### Table: User
```sql
CREATE TABLE user (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_staff BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Chỉ mục
CREATE INDEX idx_user_username ON user(username);
CREATE INDEX idx_user_email ON user(email);
```

**Ý nghĩa**:
- `id`: Định danh duy nhất của người dùng
- `username`: Tên đăng nhập (unique)
- `email`: Email liên hệ (unique)
- `password_hash`: Mật khẩu đã mã hóa (bcrypt/argon2)
- `is_staff`: True = nhân viên, False = khách hàng
- `is_active`: True = tài khoản hoạt động

#### Table: BlogPost
```sql
CREATE TABLE blog_post (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    author VARCHAR(120),
    category VARCHAR(80),
    excerpt TEXT,
    body TEXT NOT NULL,
    hero_image_url VARCHAR(500),
    published_at DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_blog_published ON blog_post(published_at DESC);
CREATE INDEX idx_blog_slug ON blog_post(slug);
```

**Ý nghĩa**: Lưu trữ bài viết blog cho SEO và nội dung editorial

#### Table: Testimonial
```sql
CREATE TABLE testimonial (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    role VARCHAR(120),
    quote TEXT NOT NULL,
    rating SMALLINT DEFAULT 5 CHECK (rating BETWEEN 1 AND 5),
    avatar_url VARCHAR(500),
    is_featured BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_testimonial_featured ON testimonial(is_featured);
```

**Ý nghĩa**: Lưu trữ lời chứng thực từ khách hàng cho trang chủ

#### Table: LegacyUserMapping
```sql
CREATE TABLE legacy_user_mapping (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    legacy_source VARCHAR(20) NOT NULL,
    legacy_user_id INT NOT NULL,
    legacy_username VARCHAR(150),
    legacy_email VARCHAR(255),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(legacy_source, legacy_user_id)
);

CREATE INDEX idx_legacy_user ON legacy_user_mapping(user_id);
```

**Ý nghĩa**: Map từ hệ thống cũ sang hệ thống mới (data migration)

---

### 2.2 MYSQL - ORDER SERVICE (order_db)

#### Table: Cart
```sql
CREATE TABLE cart (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL REFERENCES user(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_cart_user ON cart(user_id);
```

**Ý nghĩa**: 1 user = 1 giỏ hàng, giỏ chứa nhiều items

#### Table: CartItem
```sql
CREATE TABLE cart_item (
    id INT PRIMARY KEY AUTO_INCREMENT,
    cart_id INT NOT NULL REFERENCES cart(id) ON DELETE CASCADE,
    product_id INT NOT NULL,
    product_name VARCHAR(255),
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity INT DEFAULT 1,
    category_slug VARCHAR(120),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cartitem_cart ON cart_item(cart_id);
CREATE INDEX idx_cartitem_product ON cart_item(product_id);
```

**Ý nghĩa**: Mục trong giỏ hàng (snapshot pattern)
- `product_id`: Tham chiếu đến product_service.product
- `product_name`, `unit_price`: Snapshot (copy) tại thời điểm thêm vào giỏ

#### Table: SavedItem
```sql
CREATE TABLE saved_item (
    id INT PRIMARY KEY AUTO_INCREMENT,
    cart_id INT NOT NULL REFERENCES cart(id) ON DELETE CASCADE,
    product_id INT NOT NULL,
    product_name VARCHAR(255),
    unit_price DECIMAL(12, 2),
    category_slug VARCHAR(120),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_saved_cart ON saved_item(cart_id);
```

**Ý nghĩa**: Danh sách yêu thích (wishlist) của user

#### Table: CompareItem
```sql
CREATE TABLE compare_item (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL REFERENCES user(id),
    product_id INT NOT NULL,
    product_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_compare_user ON compare_item(user_id);
```

**Ý nghĩa**: So sánh sản phẩm (comparator)

#### Table: Order
```sql
CREATE TABLE order (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL REFERENCES user(id),
    status VARCHAR(50) NOT NULL,
    -- pending, paid, delivering, delivered, cancelled
    subtotal DECIMAL(12, 2),
    tax DECIMAL(12, 2),
    shipping_cost DECIMAL(12, 2),
    total_amount DECIMAL(12, 2) NOT NULL,
    payment_status VARCHAR(50),
    -- pending_payment, paid, failed, refunded
    shipping_status VARCHAR(50),
    -- pending, preparing, shipped, delivered
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX idx_order_user ON order(user_id);
CREATE INDEX idx_order_status ON order(status);
CREATE INDEX idx_order_created ON order(created_at DESC);
```

**Ý nghĩa**: Đơn hàng chính
- `status`: Trạng thái toàn bộ đơn hàng
- `payment_status`, `shipping_status`: Trạng thái chi tiết

#### Table: OrderItem
```sql
CREATE TABLE order_item (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL REFERENCES order(id) ON DELETE CASCADE,
    product_id INT NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    product_brand VARCHAR(120),
    product_image_url VARCHAR(500),
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity INT NOT NULL,
    total_price DECIMAL(12, 2) NOT NULL,
    category_slug VARCHAR(120),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orderitem_order ON order_item(order_id);
```

**Ý nghĩa**: Mục trong đơn hàng (snapshot pattern tại thời điểm order)

#### Table: OrderPaymentSnapshot
```sql
CREATE TABLE order_payment_snapshot (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL REFERENCES order(id) UNIQUE,
    payment_id INT,
    amount DECIMAL(12, 2),
    method VARCHAR(50),
    status VARCHAR(50),
    transaction_id VARCHAR(255),
    paid_at TIMESTAMP
);

CREATE INDEX idx_payment_snapshot_order ON order_payment_snapshot(order_id);
```

**Ý nghĩa**: Snapshot thông tin thanh toán từ payment_service

#### Table: OrderShippingSnapshot
```sql
CREATE TABLE order_shipping_snapshot (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL REFERENCES order(id) UNIQUE,
    shipment_id INT,
    recipient_name VARCHAR(255),
    address TEXT,
    city VARCHAR(100),
    postal_code VARCHAR(20),
    tracking_number VARCHAR(255),
    status VARCHAR(50),
    updated_at TIMESTAMP
);

CREATE INDEX idx_shipping_snapshot_order ON order_shipping_snapshot(order_id);
```

**Ý nghĩa**: Snapshot thông tin vận chuyển từ shipping_service

---

### 2.3 POSTGRESQL - PRODUCT SERVICE (product_db)

#### Table: Category
```sql
CREATE TABLE category (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT
);

CREATE INDEX idx_category_slug ON category(slug);
```

**Ý nghĩa**: 10 danh mục sản phẩm (Fashion, Electronics, v.v.)

#### Table: Shop
```sql
CREATE TABLE shop (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    phone VARCHAR(20),
    email VARCHAR(255)
);

CREATE INDEX idx_shop_name ON shop(name);
```

**Ý nghĩa**: Thương hiệu/cửa hàng bán sản phẩm

#### Table: Product
```sql
CREATE TABLE product (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock INT DEFAULT 0,
    image_url VARCHAR(500),
    category_id INT NOT NULL REFERENCES category(id),
    shop_id INT NOT NULL REFERENCES shop(id),
    brand VARCHAR(120),
    catalog_source VARCHAR(50),
    -- 'seeded', 'imported', 'manual'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX idx_product_category ON product(category_id);
CREATE INDEX idx_product_shop ON product(shop_id);
CREATE INDEX idx_product_slug ON product(slug);
CREATE INDEX idx_product_price ON product(price);
```

**Ý nghĩa**: Sản phẩm chính (~100 seeded products)

---

### 2.4 POSTGRESQL - PAYMENT SERVICE (payment_db)

#### Table: Payment
```sql
CREATE TABLE payment (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    method VARCHAR(50) NOT NULL,
    -- 'credit_card', 'e_wallet', 'bank_transfer'
    status VARCHAR(50) NOT NULL,
    -- 'pending', 'paid', 'failed', 'refunded'
    transaction_id VARCHAR(255),
    currency VARCHAR(3) DEFAULT 'USD',
    metadata JSONB,
    paid_at TIMESTAMP,
    refunded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX idx_payment_order ON payment(order_id);
CREATE INDEX idx_payment_status ON payment(status);
```

**Ý nghĩa**: Ghi nhận thanh toán từ order_service

#### Table: PaymentEvent
```sql
CREATE TABLE payment_event (
    id SERIAL PRIMARY KEY,
    payment_id INT NOT NULL REFERENCES payment(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    -- 'initiated', 'authorized', 'captured', 'failed', 'refunded'
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payment_event_payment ON payment_event(payment_id);
CREATE INDEX idx_payment_event_type ON payment_event(event_type);
```

**Ý nghĩa**: Lịch sử sự kiện của mỗi thanh toán

---

### 2.5 POSTGRESQL - SHIPPING SERVICE (shipping_db)

#### Table: Shipment
```sql
CREATE TABLE shipment (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    status VARCHAR(50) NOT NULL,
    -- 'pending', 'preparing', 'shipped', 'in_transit', 'delivered'
    recipient_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    address TEXT NOT NULL,
    city VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    tracking_number VARCHAR(255) UNIQUE,
    carrier VARCHAR(100),
    estimated_delivery DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX idx_shipment_order ON shipment(order_id);
CREATE INDEX idx_shipment_tracking ON shipment(tracking_number);
CREATE INDEX idx_shipment_status ON shipment(status);
```

**Ý nghĩa**: Ghi nhận vận chuyển từ order_service

#### Table: ShipmentTracking
```sql
CREATE TABLE shipment_tracking (
    id SERIAL PRIMARY KEY,
    shipment_id INT NOT NULL REFERENCES shipment(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    -- 'picked_up', 'in_transit', 'out_for_delivery', 'delivered'
    location VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tracking_shipment ON shipment_tracking(shipment_id);
CREATE INDEX idx_tracking_timestamp ON shipment_tracking(timestamp DESC);
```

**Ý nghĩa**: Chi tiết theo dõi gói hàng (tracking history)

---

### 2.6 POSTGRESQL - CHATBOT SERVICE (chatbot_db)

#### Table: BehaviorEvent
```sql
CREATE TABLE behavior_event (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    product_id INT,
    order_id INT,
    event_type VARCHAR(100) NOT NULL,
    -- 'search', 'view_product', 'chatbot_ask', 'save_item',
    -- 'compare_item', 'add_to_cart', 'checkout', 'pay_order'
    event_data JSONB NOT NULL,
    session_id VARCHAR(255),
    device_type VARCHAR(50),
    -- 'mobile', 'desktop', 'tablet'
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_behavior_user ON behavior_event(user_id);
CREATE INDEX idx_behavior_type ON behavior_event(event_type);
CREATE INDEX idx_behavior_timestamp ON behavior_event(timestamp DESC);
CREATE INDEX idx_behavior_product ON behavior_event(product_id);
CREATE INDEX idx_behavior_session ON behavior_event(session_id);
```

**Ý nghĩa**: Lưu trữ tất cả hành vi người dùng
- `user_id`: Tham chiếu đến user_service.user
- `product_id`: Optional, tham chiếu đến product_service.product
- `order_id`: Optional, tham chiếu đến order_service.order
- `event_data`: JSONB chứa dữ liệu chi tiết sự kiện

**Event Data Examples**:
```json
{
  "event_type": "search",
  "event_data": {
    "query": "áo khoác",
    "results_count": 12,
    "filters": {"category": "fashion", "price_min": 50}
  }
}

{
  "event_type": "chatbot_ask",
  "event_data": {
    "query": "áo khoác nữ bao nhiêu?",
    "category_predicted": "fashion",
    "response": "...",
    "confidence": 0.94,
    "suggested_products": [45, 46, 47]
  }
}

{
  "event_type": "pay_order",
  "event_data": {
    "order_id": 123,
    "amount": 299.97,
    "payment_method": "credit_card",
    "status": "paid"
  }
}
```

---

### 2.7 NEO4J - BEHAVIOR GRAPH (Optional)

#### Nodes & Relationships

```cypher
-- User Node
CREATE (:User {
  user_ref: 123,
  event_count: 45,
  session_count: 12,
  primary_category_slug: "fashion",
  affinity_total: 156.4
})

-- Behavior Node
CREATE (:Behavior {
  behavior_id: "behav_xyz",
  behavior_type: "chatbot_ask",
  event_ts: 1702225800000,
  session_id: "sess_abc",
  step_index: 5,
  price_bucket: "50-100",
  device_type: "mobile",
  search_query: "áo khoác nữ",
  target_next_category_slug: "fashion",
  affinity_weight: 2.4
})

-- Relationships
(u:User)-[:PERFORMED]->(b:Behavior)
(b:Behavior)-[:IN_CATEGORY]->(c:Category)
(b:Behavior)-[:ON_PRODUCT]->(p:Product)
(p:Product)-[:BELONGS_TO]->(c:Category)
(u:User)-[:PREFERS {
  score: 156.4,
  share: 0.45,
  rank: 1,
  event_count: 24,
  last_event_ts: 1702225800000
}]->(c:Category)
```

#### Affinity Weight Scale

| Event Type | Weight | Ý Nghĩa |
|------------|--------|---------|
| search | 1.0 | Tìm kiếm cơ bản |
| view_product | 1.6 | Xem chi tiết |
| chatbot_ask | 2.4 | Tương tác với AI |
| save_item | 3.0 | Lưu yêu thích |
| compare_item | 3.2 | So sánh sản phẩm |
| add_to_cart | 4.2 | Thêm giỏ hàng |
| checkout | 5.1 | Tiến tới thanh toán |
| pay_order | 6.0 | Thanh toán thành công |

---

## 3. MỐI QUAN HỆ CHỈ ĐẾN (CROSS-SERVICE REFERENCES)

### 3.1 Direct Foreign Keys

```
order_service.Order.user_id → user_service.user.id
order_service.CartItem.product_id → product_service.product.id
order_service.OrderItem.product_id → product_service.product.id
product_service.Product.category_id → product_service.category.id
product_service.Product.shop_id → product_service.shop.id
chatbot_service.BehaviorEvent.user_id → user_service.user.id
chatbot_service.BehaviorEvent.product_id → product_service.product.id (nullable)
chatbot_service.BehaviorEvent.order_id → order_service.order.id (nullable)
```

### 3.2 Event-Driven References (Async)

```
order_service.Order (created)
  ↓ (webhook event)
payment_service.Payment (created với order_id)

order_service.Order (created)
  ↓ (webhook event)
shipping_service.Shipment (created với order_id)

(Any service) (behavior occurs)
  ↓ (async message/event)
chatbot_service.BehaviorEvent (recorded)
```

---

## 4. SNAPSHOT PATTERN

### 4.1 Tại Sao Cần Snapshot?

**Vấn đề**: Giá sản phẩm thay đổi theo thời gian
- User A thêm sản phẩm vào giỏ lúc $99.99
- Giá thay đổi thành $79.99
- User A checkout → thanh toán bao nhiêu?

**Giải pháp**: Lưu snapshot tại thời điểm tạo order_item

### 4.2 Các Trường Snapshot

| Table | Snapshot Fields | Lý Do |
|-------|-----------------|-------|
| CartItem | product_name, unit_price | Giỏ hàng "tạm thời" nhưng cần giá chính xác |
| OrderItem | product_name, brand, image, price | Hóa đơn cần ghi lại chính xác tại thời điểm |
| SavedItem | product_name, price | Danh sách yêu thích tham chiếu |

### 4.3 Triển Khai Code

```python
# Khi thêm vào giỏ hàng
product = Product.objects.get(id=product_id)
cart_item = CartItem.objects.create(
    cart=cart,
    product_id=product.id,
    product_name=product.name,  # snapshot
    unit_price=product.price,   # snapshot
    quantity=quantity
)

# Khi checkout
for cart_item in cart.items.all():
    order_item = OrderItem.objects.create(
        order=order,
        product_id=cart_item.product_id,
        product_name=cart_item.product_name,  # keep from cart_item
        unit_price=cart_item.unit_price,      # keep from cart_item
        quantity=cart_item.quantity,
        total_price=cart_item.unit_price * cart_item.quantity
    )
```

---

## 5. INDEXING STRATEGY

### 5.1 Chỉ Mục Quan Trọng

**Frequently Queried**:
```sql
-- User Service
CREATE INDEX idx_user_username ON user(username);
CREATE INDEX idx_user_email ON user(email);

-- Order Service
CREATE INDEX idx_order_user ON order(user_id);
CREATE INDEX idx_order_status ON order(status);
CREATE INDEX idx_order_created ON order(created_at DESC);

-- Product Service
CREATE INDEX idx_product_category ON product(category_id);
CREATE INDEX idx_product_price ON product(price);

-- Chatbot Service
CREATE INDEX idx_behavior_user ON behavior_event(user_id);
CREATE INDEX idx_behavior_type ON behavior_event(event_type);
CREATE INDEX idx_behavior_timestamp ON behavior_event(timestamp DESC);
```

### 5.2 Composite Indexes

```sql
-- Tìm orders của user với status cụ thể
CREATE INDEX idx_order_user_status ON order(user_id, status);

-- Tìm events của user trong ngày
CREATE INDEX idx_behavior_user_timestamp ON behavior_event(user_id, timestamp DESC);

-- Tìm products của category có price trong range
CREATE INDEX idx_product_category_price ON product(category_id, price);
```

---

## 6. QUERIES THƯỜNG GẶP

### 6.1 Lấy Đơn Hàng Của User

```sql
SELECT o.*, oi.product_name, oi.quantity, oi.total_price
FROM order o
LEFT JOIN order_item oi ON o.id = oi.order_id
WHERE o.user_id = 123
ORDER BY o.created_at DESC;
```

### 6.2 Tính Tổng Doanh Thu

```sql
SELECT 
  DATE(o.created_at) as date,
  COUNT(*) as order_count,
  SUM(o.total_amount) as revenue
FROM order o
WHERE o.status IN ('paid', 'delivering', 'delivered')
GROUP BY DATE(o.created_at)
ORDER BY date DESC;
```

### 6.3 Hành Vi User Top

```sql
SELECT 
  user_id,
  event_type,
  COUNT(*) as event_count,
  DATE(timestamp) as date
FROM behavior_event
WHERE DATE(timestamp) = CURRENT_DATE
GROUP BY user_id, event_type, DATE(timestamp)
ORDER BY event_count DESC
LIMIT 20;
```

### 6.4 Category Affinity (Neo4j)

```cypher
MATCH (u:User {user_ref: 123})-[pref:PREFERS]->(c:Category)
RETURN c.name, pref.score as affinity_score, pref.event_count
ORDER BY affinity_score DESC
LIMIT 5;
```

---

## 7. MIGRATION & CONSTRAINTS

### 7.1 Cascade Delete Rules

```sql
-- CartItem → Cart delete
ALTER TABLE cart_item 
ADD CONSTRAINT fk_cartitem_cart 
FOREIGN KEY (cart_id) REFERENCES cart(id) 
ON DELETE CASCADE;

-- OrderItem → Order delete
ALTER TABLE order_item 
ADD CONSTRAINT fk_orderitem_order 
FOREIGN KEY (order_id) REFERENCES order(id) 
ON DELETE CASCADE;

-- PaymentEvent → Payment delete
ALTER TABLE payment_event 
ADD CONSTRAINT fk_event_payment 
FOREIGN KEY (payment_id) REFERENCES payment(id) 
ON DELETE CASCADE;
```

### 7.2 Unique Constraints

```sql
-- 1 user = 1 cart
CREATE UNIQUE INDEX idx_cart_user ON cart(user_id);

-- Category slug unique
ALTER TABLE category ADD CONSTRAINT uc_category_slug UNIQUE(slug);

-- Product tracking number unique
ALTER TABLE shipment ADD CONSTRAINT uc_tracking UNIQUE(tracking_number);
```

---

## 8. PERFORMANCE TIPS

1. **Pagination**: Luôn giới hạn kết quả với LIMIT/OFFSET
2. **Denormalization**: Lưu thêm fields (snapshot) khi cần query nhanh
3. **Archival**: Di chuyển old orders → archive table hàng quý
4. **Sharding**: Nếu quá lớn, shard theo user_id
5. **Read Replicas**: PG → replica cho read-heavy queries

---

**Xem thêm**: [TỔNG-HỢP-KIẾN-TRÚC-DỰ-ÁN.md](../TỔNG-HỢP-KIẾN-TRÚC-DỰ-ÁN.md) cho chi tiết kiến trúc AI Chatbot.
