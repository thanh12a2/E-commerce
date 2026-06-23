# 📦 kiemtra01 — Hệ Thống E-Commerce Microservices với Django

> Dự án thương mại điện tử kiến trúc microservices gồm **6 service Django**, **Nginx API Gateway**, **3 hệ quản trị CSDL** (MySQL, PostgreSQL, Neo4j), và tích hợp **AI Chatbot** với RAG + Knowledge Graph. Toàn bộ chạy trên Docker Compose.

---

## 📑 Mục Lục

1. [Tổng Quan Dự Án](#1--tổng-quan-dự-án)
2. [Kiến Trúc Hệ Thống](#2--kiến-trúc-hệ-thống)
3. [Cấu Trúc Thư Mục](#3--cấu-trúc-thư-mục)
4. [Chi Tiết Từng Service](#4--chi-tiết-từng-service)
5. [Cơ Sở Dữ Liệu](#5--cơ-sở-dữ-liệu)
6. [Cấu Hình File `.env`](#6--cấu-hình-file-env)
7. [Yêu Cầu Hệ Thống](#7--yêu-cầu-hệ-thống)
8. [Hướng Dẫn Cài Đặt & Khởi Chạy](#8--hướng-dẫn-cài-đặt--khởi-chạy)
9. [Seed Dữ Liệu & Build Artifacts](#9--seed-dữ-liệu--build-artifacts)
10. [API Routes & Endpoints](#10--api-routes--endpoints)
11. [Kiểm Tra Hệ Thống (Smoke Test)](#11--kiểm-tra-hệ-thống-smoke-test)
12. [Chatbot & AI Artifacts](#12--chatbot--ai-artifacts)
13. [Các Lệnh Thường Dùng](#13--các-lệnh-thường-dùng)
14. [Xử Lý Sự Cố](#14--xử-lý-sự-cố)

---

## 1. 🔭 Tổng Quan Dự Án

Đây là hệ thống **thương mại điện tử (e-commerce)** được xây dựng theo kiến trúc **microservices**, sử dụng framework **Django** (Python) cho backend. Hệ thống bao gồm:

- **6 application services** riêng biệt, mỗi service có database và Dockerfile riêng
- **1 API Gateway** (Nginx) là điểm truy cập duy nhất từ bên ngoài
- **3 hệ quản trị CSDL**: MySQL, PostgreSQL, Neo4j
- **AI Chatbot** tích hợp RAG (Retrieval-Augmented Generation) và Knowledge Graph
- Giao diện web cho **khách hàng** (customer) và **nhân viên** (staff)
- Hỗ trợ **2 chế độ xác thực**: Django Session (UI) và JWT (API)

### Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Backend Framework | Django 5.2 + Django REST Framework 3.17 |
| Ngôn ngữ | Python 3.12 |
| API Gateway | Nginx 1.27 Alpine |
| Database (relational) | MySQL 8.0 + PostgreSQL 16 |
| Database (graph) | Neo4j 5.26 |
| AI/ML | TensorFlow CPU 2.19, Keras 3.10 |
| LLM Provider | Google Gemma / Gemini / OpenRouter |
| Container | Docker + Docker Compose |
| Auth | Django Session + JWT (SimpleJWT) |

---

## 2. 🏗 Kiến Trúc Hệ Thống

```
                          ┌─────────────────────┐
                          │    Client/Browser    │
                          └──────────┬──────────┘
                                     │ :8080
                          ┌──────────▼──────────┐
                          │   Nginx Gateway     │
                          │   (API Gateway)     │
                          └──────────┬──────────┘
                                     │
          ┌──────────┬───────────┬───┴───┬───────────┬──────────┐
          │          │           │       │           │          │
    ┌─────▼────┐ ┌───▼────┐ ┌───▼───┐ ┌─▼────────┐ ┌▼────────┐ ┌▼──────────┐
    │  User    │ │Product │ │ Order │ │ Payment  │ │Shipping │ │ Chatbot   │
    │ Service  │ │Service │ │Service│ │ Service  │ │Service  │ │ Service   │
    │ :8000    │ │ :8001  │ │(int.) │ │ (int.)   │ │(int.)   │ │ :8005     │
    └────┬─────┘ └───┬────┘ └───┬───┘ └─┬────────┘ └┬────────┘ └┬──────────┘
         │           │         │       │           │          │
    ┌────▼─────┐ ┌───▼─────────▼───────▼───────────▼──┐  ┌───▼────┐
    │  MySQL   │ │         PostgreSQL                  │  │ Neo4j  │
    │ user_db  │ │ product_db | chatbot_db | payment_db│  │ (opt.) │
    │ order_db │ │ shipping_db                         │  └────────┘
    └──────────┘ └─────────────────────────────────────┘
```

### Luồng hoạt động chính

1. **Client** truy cập qua Nginx Gateway tại port `8080`
2. **Gateway** phân phối request đến service tương ứng dựa trên URL path
3. Mỗi **service** có database riêng, giao tiếp nội bộ qua Docker network
4. **user_service** đóng vai trò **orchestrator** — gọi đến các service khác (order, payment, shipping, chatbot) để phục vụ giao diện
5. **chatbot_service** sử dụng RAG + Neo4j Knowledge Graph + LLM (Gemma/Gemini) để sinh gợi ý sản phẩm

---

## 4. 🔍 Chi Tiết Từng Service

### 4.1. `user_service` — 👤 Xác thực & Giao diện

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Auth source chính, UI khách hàng/nhân viên, gateway/orchestrator |
| **Database** | MySQL (`user_db`) |
| **Port** | `8000`, `8003` (debug) |
| **Dependencies** | Django, DRF, SimpleJWT, PyMySQL, requests |

**Chức năng chính:**
- Đăng ký, đăng nhập khách hàng/nhân viên (Django session)
- JWT API authentication (`/api/auth/`)
- Dashboard khách hàng với gợi ý AI
- Quản lý sản phẩm cho nhân viên
- Proxy chatbot requests
- Gọi nội bộ đến `order_service`, `payment_service`, `shipping_service`, `chatbot_service`
- Migration legacy users

### 4.2. `product_service` — 📦 Catalog Sản Phẩm

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Unified catalog API (10 categories, 100 seeded products) |
| **Database** | PostgreSQL (`product_db`) |
| **Port** | `8001` (debug) |
| **Dependencies** | Django, DRF, psycopg2 |

**Chức năng chính:**
- CRUD sản phẩm (staff cần `X-Staff-Key` header)
- API categories và products
- Seed 100 sản phẩm demo với 10 danh mục

### 4.3. `order_service` — 🛒 Đơn Hàng

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Cart, saved items, compare, orders, checkout orchestration |
| **Database** | MySQL (`order_db`) |
| **Port** | Internal only (Docker network) |
| **Dependencies** | Django, DRF, PyMySQL, requests |

**Chức năng chính:**
- Giỏ hàng, lưu sản phẩm yêu thích, so sánh
- Checkout → tạo pending order → gọi `payment_service` + `shipping_service`
- Analytics đơn hàng
- Import legacy orders

### 4.4. `payment_service` — 💳 Thanh Toán

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Payment record creation & confirmation |
| **Database** | PostgreSQL (`payment_db`) |
| **Port** | Internal only |
| **Dependencies** | Django, DRF, psycopg2 |

### 4.5. `shipping_service` — 🚚 Vận Chuyển

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Shipment records & shipping status lifecycle |
| **Database** | PostgreSQL (`shipping_db`) |
| **Port** | Internal only |
| **Dependencies** | Django, DRF, psycopg2 |

### 4.6. `chatbot_service` — 🤖 AI Chatbot

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Hybrid chatbot: RAG + ML model + Neo4j graph + LLM |
| **Database** | PostgreSQL (`chatbot_db`) + Neo4j (optional) |
| **Port** | `8005` (debug) |
| **Dependencies** | Django, DRF, psycopg2, neo4j, keras, tensorflow-cpu |

**Chức năng chính:**
- Chat reply với hybrid retrieval (file RAG → ML model → Neo4j graph → LLM)
- Behavior event persistence (PostgreSQL)
- Category-affinity prediction (Keras model)
- Knowledge base build từ product catalog
- Neo4j behavior graph cho Phase 4/5 context queries
- Hỗ trợ nhiều LLM provider: Gemma, Gemini, OpenRouter

### 4.7. `gateway` — 🌐 Nginx API Gateway

| Thuộc tính | Giá trị |
|---|---|
| **Vai trò** | Reverse proxy, public entry point duy nhất |
| **Image** | `nginx:1.27-alpine` |
| **Port** | `8080` → internal port `80` |

**Routing rules:**

| URL Path | → Service |
|---|---|
| `/`, `/customer/`, `/staff/`, `/admin/`, `/gateway/`, `/api/auth/` | `user-service:8000` |
| `/api/products/`, `/api/categories/` | `product-service:8000` |
| `/api/cart/`, `/api/orders/` | `order-service:8000` |
| `/api/payments/` | `payment-service:8000` |
| `/api/shipments/` | `shipping-service:8000` |
| `/api/chat/` | `chatbot-service:8000` |

---

## 5. 🗄 Cơ Sở Dữ Liệu

### MySQL 8.0
- **Container**: `kiemtra01_mysql`
- **Databases**: `user_db` (user_service), `order_db` (order_service)
- **Init script**: `docker/mysql-init/01-create-databases.sql` — tự tạo DB, users, và grant privileges
- **Volume**: `mysql_data` (persistent)

### PostgreSQL 16
- **Container**: `kiemtra01_postgres`
- **Databases**: `product_db`, `chatbot_db`, `payment_db`, `shipping_db`
- **Init script**: `docker/postgres-init/01-create-databases.sql`
- **Volume**: `postgres_data` (persistent)

### Neo4j 5.26 (Optional)
- **Container**: `kiemtra01_neo4j`
- **Vai trò**: Knowledge graph cho chatbot behavior context
- **Ports**: `7474` (browser), `7687` (bolt protocol)
- **Volumes**: `neo4j_data`, `neo4j_logs`
- **Lưu ý**: Chatbot service vẫn hoạt động bình thường nếu Neo4j không available — tự động fallback về file-based RAG

---

## 6. ⚙️ Cấu Hình File `.env`

### Bước 1: Tạo file `.env` từ template

```powershell
copy .env.example .env
```

### Bước 2: Chỉnh sửa các biến theo nhu cầu

Dưới đây là bảng giải thích **tất cả** các biến môi trường:

### 🔐 Shared / Bảo mật

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `STAFF_API_KEY` | API key để staff tạo/sửa/xóa sản phẩm (header `X-Staff-Key`) | `dev-staff-key` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Danh sách origins được trust cho CSRF | `http://localhost:8080,...` |
| `CUSTOMER_SESSION_COOKIE_NAME` | Tên cookie session cho customer | `customer_sessionid` |
| `STAFF_SESSION_COOKIE_NAME` | Tên cookie session cho staff | `staff_sessionid` |

### 🐬 MySQL

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | Mật khẩu root MySQL | `root_password` |
| `USER_MYSQL_DATABASE` | Tên database cho user_service | `user_db` |
| `USER_MYSQL_USER` | Username kết nối user_db | `user_user` |
| `USER_MYSQL_PASSWORD` | Mật khẩu user_db | `user_password` |
| `ORDER_MYSQL_DATABASE` | Tên database cho order_service | `order_db` |
| `ORDER_MYSQL_USER` | Username kết nối order_db | `order_user` |
| `ORDER_MYSQL_PASSWORD` | Mật khẩu order_db | `order_password` |

### 🐘 PostgreSQL

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `POSTGRES_USER` | Username chung PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Mật khẩu chung PostgreSQL | `postgres` |
| `PRODUCT_POSTGRES_DB` | Database cho product_service | `product_db` |
| `CHATBOT_POSTGRES_DB` | Database cho chatbot_service | `chatbot_db` |
| `PAYMENT_POSTGRES_DB` | Database cho payment_service | `payment_db` |
| `SHIPPING_POSTGRES_DB` | Database cho shipping_service | `shipping_db` |

### 🔵 Neo4j (Optional)

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `NEO4J_URI` | Connection URI Neo4j | `bolt://neo4j:7687` |
| `NEO4J_USERNAME` | Username Neo4j | `neo4j` |
| `NEO4J_PASSWORD` | Mật khẩu Neo4j | `graph_password` |
| `NEO4J_DATABASE` | Tên database Neo4j | `neo4j` |

### 🔗 Internal Service URLs

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `USER_SERVICE_URL` | URL nội bộ user service | `http://user-service:8000` |
| `PRODUCT_SERVICE_URL` | URL nội bộ product service | `http://product-service:8000` |
| `ORDER_SERVICE_URL` | URL nội bộ order service | `http://order-service:8000` |
| `PAYMENT_SERVICE_URL` | URL nội bộ payment service | `http://payment-service:8000` |
| `SHIPPING_SERVICE_URL` | URL nội bộ shipping service | `http://shipping-service:8000` |
| `CHATBOT_SERVICE_URL` | URL nội bộ chatbot service | `http://chatbot-service:8000` |

### 🔑 Internal API Keys

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `ORDER_SERVICE_INTERNAL_KEY` | Key xác thực gọi nội bộ order service | `dev-order-internal-key` |
| `PAYMENT_SERVICE_INTERNAL_KEY` | Key xác thực gọi nội bộ payment service | `dev-order-internal-key` |
| `SHIPPING_SERVICE_INTERNAL_KEY` | Key xác thực gọi nội bộ shipping service | `dev-order-internal-key` |

### 🤖 Chatbot & AI

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `CHATBOT_REQUEST_TIMEOUT_SECONDS` | Timeout khi user_service gọi chatbot | `40` |
| `CHATBOT_REQUEST_RETRIES` | Số lần retry khi chatbot timeout | `2` |
| `CHATBOT_INGEST_KEY` | Key cho chatbot behavior ingest API | _(trống)_ |
| `LLM_PROVIDER` | Provider LLM: `gemma`, `gemini`, hoặc `openrouter` | `gemma` |
| `GEMMA_MODEL` | Model Gemma sử dụng | `gemma-4-31b-it` |
| `GEMMA_TIMEOUT_SECONDS` | Timeout gọi Gemma API | `45` |
| `GEMINI_API_KEY` | 🔑 **API key Google AI Studio** (bắt buộc nếu dùng gemma/gemini) | _(cần điền)_ |
| `CHATBOT_GEMINI_MODEL` | Model Gemini sử dụng | `gemini-3.1-flash-lite-preview` |
| `GEMINI_TIMEOUT_SECONDS` | Timeout gọi Gemini API | `35` |
| `OPENROUTER_API_KEY` | API key OpenRouter (nếu dùng) | _(trống)_ |
| `OPENROUTER_BASE_URL` | Base URL OpenRouter | `https://openrouter.ai/api/v1/chat/completions` |
| `OPENROUTER_SITE_URL` | Site URL cho OpenRouter tracking | _(trống)_ |
| `OPENROUTER_APP_NAME` | App name cho OpenRouter | `kiemtra01-chatbot` |

> **⚠️ Lưu ý quan trọng:** Nếu dùng `LLM_PROVIDER=gemma` hoặc `gemini`, bạn **bắt buộc** phải có `GEMINI_API_KEY` hợp lệ từ [Google AI Studio](https://aistudio.google.com/apikey). Nếu không có key, chatbot sẽ fallback về rule-based generation.

---

## 7. 💻 Yêu Cầu Hệ Thống

| Yêu cầu | Chi tiết |
|---|---|
| **Docker Desktop** | Phiên bản mới nhất, đã chạy |
| **Docker Compose** | V2 (tích hợp trong Docker Desktop) |
| **RAM** | Tối thiểu **8 GB** (khuyến nghị 12–16 GB vì có TensorFlow + Neo4j) |
| **Disk** | Tối thiểu **10 GB** trống cho Docker images |
| **Ports trống** | `8080`, `8000`, `8001`, `8003`, `8005`, `7474`, `7687` |
| **OS** | Windows 10/11, macOS, Linux |

---

## 8. 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy

### Bước 1: Clone repository

```powershell
git clone <repository-url>
cd kiemtra01-codex-TieuLuan01
```

### Bước 2: Tạo file `.env`

```powershell
copy .env.example .env
```

Mở file `.env` và chỉnh sửa các giá trị nếu cần (xem [mục 6](#6--cấu-hình-file-env)).  
Với môi trường **development/local**, các giá trị mặc định trong `.env.example` đã đủ để chạy.

### Bước 3: Đảm bảo Docker đang chạy

```powershell
# Windows: Mở Docker Desktop
# Hoặc start service bằng PowerShell (cần quyền Admin)
Start-Service -Name com.docker.service
```

### Bước 4: Build và khởi chạy toàn bộ

```powershell
docker compose up --build -d
```

Lệnh này sẽ:
1. Build Docker image cho 6 services từ `services/*/Dockerfile`
2. Pull images: `mysql:8.0`, `postgres:16`, `neo4j:5.26`, `nginx:1.27-alpine`
3. Tạo Docker network nội bộ
4. Khởi chạy databases → healthcheck → khởi chạy services
5. Mỗi service tự động: `bootstrap DB` → `migrate` → `runserver`

> ⏱ Lần đầu build có thể mất **5-15 phút** (do pull images + install dependencies).

### Bước 5: Kiểm tra trạng thái

```powershell
# Xem tất cả containers
docker compose ps -a

# Xem logs (120 dòng cuối)
docker compose logs --tail=120 gateway user_service product_service order_service payment_service shipping_service chatbot_service
```

### Bước 6: Truy cập

| URL | Mô tả |
|---|---|
| `http://localhost:8080/` | 🌐 **Gateway chính** — điểm truy cập duy nhất |
| `http://localhost:8080/customer/register/` | Đăng ký tài khoản khách hàng |
| `http://localhost:8080/customer/login/` | Đăng nhập khách hàng |
| `http://localhost:8080/customer/dashboard/` | Dashboard + AI gợi ý |
| `http://localhost:8080/staff/login/` | Đăng nhập nhân viên |
| `http://localhost:8080/staff/dashboard/` | Dashboard nhân viên |
| `http://localhost:8080/gateway/` | Trang kiểm tra gateway |
| `http://localhost:7474/` | Neo4j Browser (user: `neo4j`, pass: `graph_password`) |

### Dừng hệ thống

```powershell
docker compose down
```

### Dừng và xóa toàn bộ data (reset hoàn toàn)

```powershell
docker compose down -v
```

> ⚠️ Flag `-v` sẽ xóa tất cả Docker volumes (MySQL data, PostgreSQL data, Neo4j data). Dùng khi muốn reset hoàn toàn.

---

## 9. 🌱 Seed Dữ Liệu & Build Artifacts

Sau khi `docker compose up` chạy thành công, thực hiện các bước sau để có dữ liệu demo:

### Chạy migrations (thường tự động, nhưng có thể chạy lại nếu cần)

```powershell
docker compose exec user_service python manage.py migrate
docker compose exec order_service python manage.py migrate
docker compose exec payment_service python manage.py migrate
docker compose exec shipping_service python manage.py migrate
docker compose exec product_service python manage.py migrate
docker compose exec chatbot_service python manage.py migrate
```

### Seed dữ liệu sản phẩm & nội dung

```powershell
# Seed 100 sản phẩm demo với 10 danh mục
docker compose exec product_service python manage.py seed_products --reset

# Seed nội dung editorial (bài viết, banner)
docker compose exec user_service python manage.py seed_editorial_content --reset
```

### Build AI artifacts cho chatbot

```powershell
# Build knowledge base từ product catalog (RAG)
docker compose exec chatbot_service python manage.py build_chat_kb --max-products 160

# Train behavior model (category prediction)
docker compose exec chatbot_service python manage.py train_behavior_model

# Import behavior graph vào Neo4j
docker compose exec chatbot_service python manage.py import_behavior_graph --reset
```

---

## 10. 🛤 API Routes & Endpoints

### Customer Routes (Browser UI)

| Route | Mô tả |
|---|---|
| `/customer/login/` | Đăng nhập |
| `/customer/register/` | Đăng ký |
| `/customer/dashboard/` | Dashboard + AI gợi ý |
| `/customer/products/<category_slug>/<id>/` | Chi tiết sản phẩm |
| `/customer/cart/` | Giỏ hàng + AI gợi ý "Có thể mua kèm" |
| `/customer/orders/` | Lịch sử đơn hàng |
| `/customer/chatbot/reply/` | Chat widget (proxy → chatbot_service) |

### Staff Routes (Browser UI)

| Route | Mô tả |
|---|---|
| `/staff/login/` | Đăng nhập nhân viên |
| `/staff/register/` | Đăng ký nhân viên |
| `/staff/dashboard/` | Dashboard nhân viên |
| `/staff/items/` | Quản lý sản phẩm |
| `/staff/customers/` | Quản lý khách hàng |
| `/staff/orders/` | Quản lý đơn hàng + cập nhật shipping |

### REST API Endpoints

| Method | Endpoint | Auth | Service |
|---|---|---|---|
| `POST` | `/api/auth/register/` | None | user_service |
| `POST` | `/api/auth/token/` | None | user_service |
| `POST` | `/api/auth/token/refresh/` | JWT | user_service |
| `GET` | `/api/auth/me/` | JWT | user_service |
| `GET` | `/api/categories/` | None | product_service |
| `GET` | `/api/products/` | None | product_service |
| `GET` | `/api/products/<id>/` | None | product_service |
| `POST/PUT/DELETE` | `/api/products/...` | `X-Staff-Key` | product_service |
| `POST` | `/api/chat/reply/` | None | chatbot_service |

---

## 11. ✅ Kiểm Tra Hệ Thống (Smoke Test)

### PowerShell (qua Gateway port 8080)

```powershell
# Test customer login page
Invoke-WebRequest http://localhost:8080/customer/login/ | Select-Object -ExpandProperty StatusCode

# Test staff login page
Invoke-WebRequest http://localhost:8080/staff/login/ | Select-Object -ExpandProperty StatusCode

# Test gateway page
Invoke-WebRequest http://localhost:8080/gateway/ | Select-Object -ExpandProperty StatusCode

# Test product API
Invoke-WebRequest http://localhost:8080/api/categories/ | Select-Object -ExpandProperty StatusCode

# Test register + chatbot
$smokeUser = "smoke_" + (Get-Date -Format "yyyyMMddHHmmss")
$authBody = @{username=$smokeUser; email="$smokeUser@example.test"; password="SmokePass123!"; confirm_password="SmokePass123!"} | ConvertTo-Json
Invoke-WebRequest http://localhost:8080/api/auth/register/ -Method Post -ContentType 'application/json' -Body $authBody | Select-Object -ExpandProperty StatusCode

# Test chatbot reply
Invoke-WebRequest http://localhost:8080/api/chat/reply/ -Method Post -ContentType 'application/json' -Body '{"message":"goi y laptop hoc tap"}' | Select-Object -ExpandProperty StatusCode
```

Tất cả lệnh trên phải trả về `200` hoặc `201`.

---

## 12. 🤖 Chatbot & AI Artifacts

Các file artifacts của chatbot được bind-mount từ host vào container tại:

```
services/chatbot_service/chatbot/artifacts/
```

| File | Mô tả |
|---|---|
| `knowledge_base.json` | RAG knowledge base (build từ product catalog) |
| `model_behavior.json` | Behavior model metadata |
| `model_best.keras` | Keras model cho category prediction |
| `label_encoder.json` | Label encoder cho model |
| `tokenizer_or_vocab.json` | Tokenizer/vocabulary cho model |
| `training_data_behavior.json` | Training data |
| `runtime_config.json` | Runtime configuration |
| `behavior_graph_demo.svg` | Demo graph visualization |

### LLM Provider Pipeline

```
User Message
    │
    ▼
┌──────────────────┐
│ File-based RAG   │ ← knowledge_base.json
└────────┬─────────┘
         │
    ▼ (optional)
┌──────────────────┐
│ ML Category      │ ← model_best.keras (nếu có)
│ Prediction       │
└────────┬─────────┘
         │
    ▼ (optional)
┌──────────────────┐
│ Neo4j Graph      │ ← Behavior context queries
│ Context          │
└────────┬─────────┘
         │
    ▼
┌──────────────────┐
│ LLM Generation   │ ← Gemma / Gemini / OpenRouter
└──────────────────┘
         │
    ▼
  AI Response
```

> Nếu Neo4j hoặc ML model không khả dụng, hệ thống tự động fallback về các bước trước đó.

---

## 13. 🔧 Các Lệnh Thường Dùng

```powershell
# Khởi chạy
docker compose up --build -d

# Xem trạng thái
docker compose ps -a

# Xem logs 1 service
docker compose logs --tail=100 -f user_service

# Restart 1 service
docker compose restart user_service

# Rebuild 1 service
docker compose up --build -d user_service

# Vào shell container
docker compose exec user_service bash

# Chạy Django shell
docker compose exec user_service python manage.py shell

# Chạy tests
docker compose exec user_service python manage.py test
docker compose exec product_service python manage.py test

# Dừng
docker compose down

# Dừng + xóa data
docker compose down -v
```

---

## 14. 🔥 Xử Lý Sự Cố

### Docker không chạy

```powershell
# Kiểm tra Docker service
Get-Service -Name com.docker.service

# Khởi động Docker service (cần Admin)
Start-Service -Name com.docker.service
```

### Port bị chiếm

```powershell
# Kiểm tra port nào đang dùng
netstat -ano | findstr :8080
netstat -ano | findstr :8000

# Kill process (thay PID)
taskkill /PID <PID> /F
```

### MySQL/Postgres không khởi tạo DB

```powershell
# Xóa volumes cũ và chạy lại
docker compose down -v
docker compose up --build -d
```

### Service không kết nối được database

```powershell
# Xem logs database
docker compose logs mysql
docker compose logs postgres

# Kiểm tra healthcheck
docker compose ps
# Cột STATUS phải hiện "healthy"
```

### Chatbot trả về lỗi

1. Kiểm tra `GEMINI_API_KEY` trong `.env` đã được điền và hợp lệ
2. Kiểm tra `LLM_PROVIDER` đúng giá trị (`gemma`, `gemini`, hoặc `openrouter`)
3. Chạy lại build KB:
   ```powershell
   docker compose exec chatbot_service python manage.py build_chat_kb --max-products 160
   ```
4. Xem logs chatbot:
   ```powershell
   docker compose logs --tail=200 chatbot_service
   ```

### Neo4j không hoạt động

> Không ảnh hưởng đến các service khác. Chatbot tự động fallback về file-based RAG.

```powershell
# Kiểm tra Neo4j
docker compose logs neo4j

# Truy cập Neo4j Browser
# http://localhost:7474/ (user: neo4j, pass: graph_password)
```

---

> 📌 **Ghi nhớ**: Luôn truy cập qua **Gateway** (`http://localhost:8080/`) cho trải nghiệm production. Các port trực tiếp (`8000`, `8001`, `8005`) chỉ dùng khi debug.
