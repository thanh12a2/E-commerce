# Visual Paradigm Relationship Guide

This guide lists the relationships to draw manually in Visual Paradigm for:

- `ANALYSIS/analysis_class_diagram.puml`
- `DATAMODEL/database_erd.puml`
- `DATAMODEL/orm_persistent_datamodel.puml`
- `DESIGN/design_package_class_diagram.puml`

Legend:

- `Association`: normal solid line.
- `Dependency`: dashed arrow from source to target.
- `Aggregation - shared`: hollow diamond. Put the diamond at the whole/owner side.
- `Composition - composite`: filled diamond. Put the diamond at the whole/owner side.

Only use diamonds on the relationships explicitly marked as `Aggregation - shared` or `Composition - composite`. Logical ID links, editorial text/content context links, snapshot links, service calls, and DTO references should not use diamonds.

## 1. Analysis Class Diagram

File:

```text
EssayV1/visual_paradigm_puml/ANALYSIS/analysis_class_diagram.puml
```

### User Content

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| Customer | BlogPost | Association | Customer `0..1`, BlogPost `0..*` | Solid line; label `author text`. |
| Customer | Testimonial | Association | Customer `0..1`, Testimonial `0..*` | Solid line; label `testimonial content`. |

Reason: this is an analysis/business diagram. `BlogPost.author` is a plain string and `Testimonial` has no FK to `auth_user`, but in the business model they are still customer-facing editorial/content concepts.

### Catalog

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| Category | Product | Aggregation - shared | Category `1`, Product `0..*` | Hollow diamond at `Category`; label `shared catalog group`. |

Reason: a product belongs to a category, but category deletion is protected in Django rather than cascading product deletion.

### Customer Commerce State

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| Customer | CartItem | Association | Customer `1`, CartItem `0..*` | Solid line; label `owns active cart`. |
| Customer | SavedItem | Association | Customer `1`, SavedItem `0..*` | Solid line; label `saves`. |
| Customer | CompareItem | Association | Customer `1`, CompareItem `0..*` | Solid line; label `compares`. |
| Customer | Order | Association | Customer `1`, Order `0..*` | Solid line; label `places`. |

Reason: draw these as business associations in the analysis diagram. The implementation stores `user_id`, not a real FK to `auth_user`, but the business relationship is customer-owned commerce state.

### Product Snapshot References

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| CartItem | Product | Association | CartItem `0..*`, Product `1` | Solid line; label `product snapshot`. |
| SavedItem | Product | Association | SavedItem `0..*`, Product `1` | Solid line; label `product snapshot`. |
| CompareItem | Product | Association | CompareItem `0..*`, Product `1` | Solid line; label `product snapshot`. |
| OrderItem | Product | Association | OrderItem `0..*`, Product `1` | Solid line; label `product snapshot`. |

Reason: draw these as business associations in analysis. The implementation keeps copied product snapshot fields and `product_id`, not a direct DB FK.

### Order

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| Order | OrderItem | Composition - composite | Order `1`, OrderItem `1..*` | Filled diamond at `Order`; label `composite checkout items`. |
| Order | OrderShipping | Composition - composite | Order `1`, OrderShipping `0..1` | Filled diamond at `Order`; label `composite shipping address`. |

Reason: in the business flow, checkout creates an order with one or more line items. `OrderItem` and `OrderShipping` are owned by `Order` with cascade delete in `order_service`.

### Payment And Shipping

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| Order | Payment | Association | Order `1`, Payment `0..1` | Solid line; label `payment record`. |
| Order | Shipment | Association | Order `1`, Shipment `0..1` | Solid line; label `shipment record`. |
| Payment | Customer | Association | Payment `0..*`, Customer `1` | Solid line; label `paid by`. |
| Shipment | Customer | Association | Shipment `0..*`, Customer `1` | Solid line; label `delivered to`. |

Reason: this is the business view of payment and shipment. In implementation, `Payment` and `Shipment` are separate services and reference `order_id` / `user_id` by value.

### AI Consultation

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| Customer | BehaviorEvent | Association | Customer `1`, BehaviorEvent `0..*` | Solid line; label `asks / browses`. |
| Customer | ChatbotReply | Association | Customer `1`, ChatbotReply `0..*` | Solid line; label `receives`. |
| BehaviorEvent | Category | Association | BehaviorEvent `0..*`, Category `0..1` | Solid line; label `category context`. |
| BehaviorEvent | Product | Association | BehaviorEvent `0..*`, Product `0..1` | Solid line; label `product context`. |
| ChatbotReply | Recommendation | Aggregation - shared | ChatbotReply `1`, Recommendation `0..*` | Hollow diamond at `ChatbotReply`; label `shared response list`. |
| Recommendation | Product | Association | Recommendation `0..*`, Product `1` | Solid line; label `recommends`. |
| Recommendation | Category | Association | Recommendation `0..*`, Category `0..1` | Solid line; label `category context`. |

Reason: `ChatbotReply` and `Recommendation` are API response DTO concepts, not database tables. `BehaviorEvent` is persisted, but it does not store a FK/reference to a reply row.

## 2. ORM Persistent / Data Model

File:

```text
EssayV1/visual_paradigm_puml/DATAMODEL/orm_persistent_datamodel.puml
```

### User Service

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| auth_user | customer_legacyusermapping | Composition - composite | auth_user `1`, customer_legacyusermapping `0..*` | Filled diamond at `auth_user`; label `composite cascade mapping`. |
| auth_user | customer_blogpost | Association - logical/editorial context | auth_user `0..1`, customer_blogpost `0..*` | Solid line; label `author text non-FK`. |
| auth_user | customer_testimonial | Association - logical/editorial context | auth_user `0..1`, customer_testimonial `0..*` | Solid line; label `testimonial content non-FK`. |

Reason: `LegacyUserMapping.user` is a real FK with `on_delete=CASCADE`, so the mapping row follows the user lifecycle. `BlogPost.author` is a plain text field and `Testimonial` has no `AuthUser` FK, but drawing logical/editorial context associations keeps the content tables attached to the user-service business context. These two content associations are not FK relationships and must not use diamonds.

### Product Service

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| catalog_category | catalog_product | Aggregation - shared | catalog_category `1`, catalog_product `0..*` | Hollow diamond at `catalog_category`; label `shared catalog group`. |

Reason: `Product.category` is a real FK with `on_delete=PROTECT`.

### Order Service

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| orders_order | orders_orderitem | Composition - composite | orders_order `1`, orders_orderitem `0..*` | Filled diamond at `orders_order`; label `composite cascade items`. |
| orders_order | orders_ordershipping | Composition - composite | orders_order `1`, orders_ordershipping `0..1` | Filled diamond at `orders_order`; label `composite cascade address`. |

Reason: `OrderItem.order` and `OrderShipping.order` cascade with `Order`. The ORM/database does not enforce `1..*` order items even though checkout creates at least one item.

### Cross-Service References

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| auth_user | orders_cartitem | Association - logical | auth_user `1`, orders_cartitem `0..*` | Solid line; label `user_id logical`. |
| auth_user | orders_saveditem | Association - logical | auth_user `1`, orders_saveditem `0..*` | Solid line; label `user_id logical`. |
| auth_user | orders_compareitem | Association - logical | auth_user `1`, orders_compareitem `0..*` | Solid line; label `user_id logical`. |
| auth_user | orders_order | Association - logical | auth_user `1`, orders_order `0..*` | Solid line; label `user_id logical`. |
| orders_cartitem | catalog_product | Association - snapshot | orders_cartitem `0..*`, catalog_product `1` | Solid line; label `product snapshot`. |
| orders_saveditem | catalog_product | Association - snapshot | orders_saveditem `0..*`, catalog_product `1` | Solid line; label `product snapshot`. |
| orders_compareitem | catalog_product | Association - snapshot | orders_compareitem `0..*`, catalog_product `1` | Solid line; label `product snapshot`. |
| orders_orderitem | catalog_product | Association - snapshot | orders_orderitem `0..*`, catalog_product `1` | Solid line; label `product snapshot`. |
| orders_order | payments_payment | Association - logical | orders_order `1`, payments_payment `0..1` | Solid line; label `order_id logical`. |
| orders_order | shipments_shipment | Association - logical | orders_order `1`, shipments_shipment `0..1` | Solid line; label `order_id logical`. |
| payments_payment | auth_user | Association - logical | payments_payment `0..*`, auth_user `1` | Solid line; label `user_id logical`. |
| shipments_shipment | auth_user | Association - logical | shipments_shipment `0..*`, auth_user `1` | Solid line; label `user_id logical`. |

Reason: these are logical ORM/data-model associations for readability. They are ID-based across service databases or copied product snapshots, not physical FK constraints. Draw them as normal associations with labels, not shared/composite relationships.

### Chatbot Service

| Source | Target | VP Relationship | Multiplicity | Diamond / Arrow |
|---|---|---|---|---|
| auth_user | chatbot_behaviorevent | Association - logical | auth_user `1`, chatbot_behaviorevent `0..*` | Solid line; label `user_ref logical`. |
| chatbot_behaviorevent | catalog_category | Association - logical | chatbot_behaviorevent `0..*`, catalog_category `0..1` | Solid line; label `category_slug logical`. |
| chatbot_behaviorevent | catalog_product | Association - logical | chatbot_behaviorevent `0..*`, catalog_product `0..1` | Solid line; label `product_id logical`. |

Reason: chatbot service stores `user_ref`, `category_slug`, and `product_id`, not physical FK constraints.

## 3. Database ERD

File:

```text
EssayV1/visual_paradigm_puml/DATAMODEL/database_erd.puml
```

For ERD in Visual Paradigm, draw physical FK relationships as solid crow's-foot relationships. Draw logical editorial/content context relationships and cross-service ID/snapshot relationships as dashed crow's-foot associations and label them as non-FK/logical references. ERD notation should stay crow's-foot; do not add UML diamonds in the ERD view.

### Physical FK Relationships

| Parent Table | Child Table | FK Column | VP Relationship | Multiplicity |
|---|---|---|---|---|
| `auth_user` | `customer_legacyusermapping` | `user_id` | Solid FK; composite equivalent in UML class/data model | `auth_user 1` to `customer_legacyusermapping 0..*` |
| `catalog_category` | `catalog_product` | `category_id` | Solid FK; shared aggregation equivalent in UML class/data model | `catalog_category 1` to `catalog_product 0..*` |
| `orders_order` | `orders_orderitem` | `order_id` | Solid FK; composite equivalent in UML class/data model | `orders_order 1` to `orders_orderitem 0..*` |
| `orders_order` | `orders_ordershipping` | `order_id` | Solid FK; composite equivalent in UML class/data model | `orders_order 1` to `orders_ordershipping 0..1` |

In the ERD, the labels `composite cascade` and `shared protect` are documentation cues only. Use actual UML diamonds only in the analysis, ORM persistent, and design class diagrams.

### Logical In-Service Editorial Content Context

| Source Table | Target Table | Reference Column | VP Relationship |
|---|---|---|---|
| `auth_user` | `customer_blogpost` | none; `author` is display text | Dashed crow-foot editorial context association; label `editorial author text non-FK`. |
| `auth_user` | `customer_testimonial` | none; testimonial fields are display content | Dashed crow-foot editorial context association; label `testimonial content non-FK`. |

Reason: `customer_blogpost` and `customer_testimonial` are standalone editorial/marketing content tables in `user_db`. The dashed links attach them to the user-service domain for diagram readability, but they do not mean `author`, `name`, or `role` references `auth_user.id`; there is no FK column in the current source code.

### Logical Cross-Service References

| Source Table | Target Table | Reference Column | VP Relationship |
|---|---|---|---|
| `auth_user` | `orders_cartitem` | `user_id` | Dashed crow-foot logical association, not FK. |
| `auth_user` | `orders_saveditem` | `user_id` | Dashed crow-foot logical association, not FK. |
| `auth_user` | `orders_compareitem` | `user_id` | Dashed crow-foot logical association, not FK. |
| `auth_user` | `orders_order` | `user_id` | Dashed crow-foot logical association, not FK. |
| `catalog_product` | `orders_cartitem` | `product_id` snapshot | Dashed crow-foot snapshot association, not FK. |
| `catalog_product` | `orders_saveditem` | `product_id` snapshot | Dashed crow-foot snapshot association, not FK. |
| `catalog_product` | `orders_compareitem` | `product_id` snapshot | Dashed crow-foot snapshot association, not FK. |
| `catalog_product` | `orders_orderitem` | `product_id` snapshot | Dashed crow-foot snapshot association, not FK. |
| `orders_order` | `payments_payment` | `order_id` | Dashed crow-foot logical association, not FK. |
| `orders_order` | `shipments_shipment` | `order_id` | Dashed crow-foot logical association, not FK. |
| `auth_user` | `payments_payment` | `user_id` | Dashed crow-foot logical association, not FK. |
| `auth_user` | `shipments_shipment` | `user_id` | Dashed crow-foot logical association, not FK. |
| `auth_user` | `chatbot_behaviorevent` | `user_ref` | Dashed crow-foot logical association, not FK. |
| `catalog_category` | `chatbot_behaviorevent` | `category_slug` | Dashed crow-foot logical association, not FK. |
| `catalog_product` | `chatbot_behaviorevent` | `product_id` | Dashed crow-foot logical association, not FK. |

## 4. Design Package/Class Diagram

File:

```text
EssayV1/visual_paradigm_puml/DESIGN/design_package_class_diagram.puml
```

This diagram is not a database diagram. It shows implementation modules and dependencies from the current Django services. Several nodes are module/facade nodes drawn with class shapes for Visual Paradigm readability, not literal Python classes.

### Package Layout

Draw these main packages:

| Package | Meaning |
|---|---|
| `gateway` | Nginx public reverse proxy. |
| `user_service` | Customer/staff UI, JWT auth, service clients, forms, user/content models. |
| `product_service` | Catalog API with DRF viewsets, serializers, models. |
| `order_service` | Cart/order API and checkout orchestration. |
| `payment_service` | Internal payment lifecycle API. |
| `shipping_service` | Internal shipment lifecycle API. |
| `chatbot_service` | AI reply, RAG, behavior model, Neo4j graph context. |

Inside each service package, group nodes into smaller packages named `controller`, `service`, `serializer`, and `model`. Use stereotypes such as `<<module facade>>`, `<<view facade>>`, or `<<module>>` where the source is function-based.

### Important Design Relationships

| Source | Target | VP Relationship | Notes |
|---|---|---|---|
| `NginxGateway` | `CustomerViews`, `StaffViews`, `AuthApiViews`, `ProductViewSet`, `CategoryViewSet`, `OrderViews`, `PaymentViews`, `ShipmentViews`, `ChatbotViews` | Dependency | Dashed arrows from gateway to controllers; `/staff` routes to `StaffViews`, `/`, `/customer`, and `/gateway` route to `CustomerViews`. |
| `CustomerViews` | `CustomerServiceClient` | Association | Customer UI delegates catalog/cart/order/chatbot calls. |
| `StaffViews` | `CustomerServiceClient` | Association | Staff UI delegates order analytics and shipping updates. |
| `AuthApiViews` | `RegisterSerializer`, `AuthTokenSerializer`, `AuthRules` | Association | JWT API validation and role payload. |
| `CustomerViews` | `CustomerForms`, `AuthRules` | Association | UI form validation and access rules. |
| `StaffViews` | `StaffForms`, `AuthRules` | Association | Staff form validation and staff-only access. |
| `CustomerServiceClient` | `GatewayRegistry` | Association | Uses the local registry/service map. |
| `RegisterSerializer`, `AuthTokenSerializer` | `AuthUser` | Association | Create/authenticate user accounts. |
| `AuthUser` | `LegacyUserMapping` | Composition - composite | Filled diamond at `AuthUser`; legacy mapping rows cascade with the user. |
| `CategoryViewSet` | `CategorySerializer` | Association | DRF serializer usage. |
| `ProductViewSet` | `ProductSerializer` | Association | DRF serializer usage. |
| `ProductViewSet` | `StaffWritePermission` | Dependency | Enforces staff-only product writes. |
| `CategorySerializer` | `Category` | Association | Serializer maps model. |
| `ProductSerializer` | `Product` | Association | Serializer maps model. |
| `Category` | `Product` | Aggregation - shared | Hollow diamond at `Category`; shared catalog grouping, not product lifecycle ownership. |
| `OrderViews` | `OrderServiceClients` | Association | Checkout orchestration uses downstream clients. |
| `OrderViews` | `CartItem`, `SavedItem`, `CompareItem`, `Order` | Association | Mutates cart/saved/compare state and creates/queries orders. |
| `Order` | `OrderItem` | Composition - composite | Filled diamond at `Order`; composite cascade ownership. |
| `Order` | `OrderShipping` | Composition - composite | Filled diamond at `Order`; composite cascade ownership. |
| `OrderServiceClients` | `PaymentViews`, `ShipmentViews` | Dependency | REST calls with internal key. |
| `PaymentViews` | `PaymentSerializer`, `PaymentInternalKeyPermission` | Association | Internal payment API validation. In source this class is named `InternalKeyPermission`; the diagram aliases it for the payment service. |
| `PaymentSerializer` | `Payment` | Association | Serializer maps model. |
| `ShipmentViews` | `ShipmentSerializer`, `ShipmentInternalKeyPermission` | Association | Internal shipment API validation. In source this class is named `InternalKeyPermission`; the diagram aliases it for the shipping service. |
| `ShipmentSerializer` | `Shipment` | Association | Serializer maps model. |
| `ChatbotViews` | `ChatbotService`, `BehaviorAI` | Association | Reply endpoint and behavior ingest endpoint. |
| `ChatbotService` | `RAGKnowledgeBase`, `BehaviorAI`, `BehaviorGraphRetriever` | Association | Hybrid AI pipeline. `ChatbotService`, `RAGKnowledgeBase`, and `BehaviorAI` are module/facade nodes. |
| `BehaviorAI` | `BehaviorEvent`, `ModelArtifacts` | Association | Behavior events are persisted; behavior/model artifacts are file based. |
| `RAGKnowledgeBase` | `ModelArtifacts` | Association | Uses `knowledge_base.json`. |
| `BehaviorGraphRetriever` | `Neo4j behavior graph` | Dependency | Optional graph context query. |
| `RAGKnowledgeBase` | `ProductViewSet` | Dependency | Builds product documents from catalog API. |

### Database Dependencies

Draw dashed dependencies from models to databases:

| Model Group | Database |
|---|---|
| `AuthUser`, `BlogPost`, `Testimonial`, `LegacyUserMapping` | `MySQL user_db` |
| `Category`, `Product` | `PostgreSQL product_db` |
| `CartItem`, `SavedItem`, `CompareItem`, `Order`, `OrderItem`, `OrderShipping` | `MySQL order_db` |
| `Payment` | `PostgreSQL payment_db` |
| `Shipment` | `PostgreSQL shipping_db` |
| `BehaviorEvent` | `PostgreSQL chatbot_db` |
