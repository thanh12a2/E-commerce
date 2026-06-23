## Plan: Demo Chatbot E-commerce Trong 1 Dem + 1 Buoi Sang

Muc tieu revised: hoan thanh chatbot demo co the tu van san pham + goi y san pham tuong tu cho nguoi dung trong thoi gian rat ngan. Khong train deep learning model. Uu tien tan dung code hien tai va lam toi gian de chay on dinh.

**Phan bo thoi gian**
1. Toi nay (khoang 4-6h): xay chatbot backend co RAG toi gian + recommendation similar products.
2. Sang mai (khoang 3-4h): tich hop UI, test demo flow, chot KPI va slide noi.

**Steps**
1. Scope sieu gon (30 phut)
   - Chi giu 2 intent:
   - Tu van san pham theo nhu cau (RAG)
   - Goi y san pham tuong tu (same category/service + same brand hoac gan khoang gia)
   - Loai bo toan bo muc train deep learning khoi dot demo nay.
2. Cach trien khai de nhanh (1-1.5h, phu thuoc step 1)
   - Khong tao microservice moi de tranh tang do phuc tap Docker.
   - Dat chatbot endpoint ngay trong customer_service de tai su dung auth/session va du lieu user.
   - Chi dung 1 endpoint chat don gian cho demo.
3. KB + retrieval toi gian (1.5-2h, phu thuoc step 2)
   - Nguon tri thuc:
   - Product tu 3 catalog services (name, description, brand, price, stock)
   - FAQ/blog co san
   - Co che retrieval:
   - Ban dau dung lexical retrieval + filter metadata (khong can vector DB neu thieu thoi gian)
   - Neu con thoi gian thi bo sung embedding API va top-k retrieval.
4. Recommendation similar products (1-1.5h, co the song song mot phan voi step 3)
   - Rule score de nhanh:
   - + diem neu cung service/category
   - + diem neu cung brand
   - + diem neu gia gan nhau
   - + diem neu con stock
   - Output top 3-5 san pham de chatbot tra ve.
5. UI widget demo (1h, phu thuoc step 3 va step 4)
   - Them chat box gon trong dashboard.
   - Render cau tra loi + danh sach product goi y co nut xem chi tiet/add cart.
6. Kiem thu va chot demo (1-1.5h, phu thuoc step 5)
   - Test 10 prompt Viet + 10 prompt Anh.
   - Test tinh huong fallback khi API LLM loi/cham.
   - Chot script demo 3-5 phut: hoi nhu cau -> chatbot tra loi -> goi y san pham -> add cart.

**Relevant files**
- c:/Users/nguye/Desktop/kiemtra01/services/customer_service/customer/views.py - them chat endpoint va logic dieu phoi RAG + recommendation.
- c:/Users/nguye/Desktop/kiemtra01/services/customer_service/customer/services.py - tai su dung fetch product, them helper retrieval/ranking.
- c:/Users/nguye/Desktop/kiemtra01/services/customer_service/customer/urls.py - them route chatbot.
- c:/Users/nguye/Desktop/kiemtra01/services/customer_service/templates/customer/dashboard.html - them chat widget va danh sach goi y.
- c:/Users/nguye/Desktop/kiemtra01/services/customer_service/requirements.txt - them thu vien LLM client nhe.
- c:/Users/nguye/Desktop/kiemtra01/docker-compose.yml - them env var API key cho customer_service.

**Verification**
1. Functional:
   - Prompt tu van co tra ve de xuat hop le.
   - Prompt tim san pham tuong tu tra ve top 3-5 ket qua.
2. Reliability:
   - Khi LLM timeout, he thong tra ve thong diep fallback + de xuat san pham co san.
3. Demo-ready:
   - End-to-end: login -> chat -> xem chi tiet san pham -> add cart thanh cong.
4. Song ngu:
   - Dung duoc voi ca Viet va Anh o muc co the demo.

**KPI de chot cho bai cham (phu hop demo ngan han)**
1. Task completion rate:
   - Ty le prompt ma chatbot tra loi dung muc tieu (tu van hoac goi y) tren bo 20 prompt test.
   - Muc tieu de nghi: >= 75%.
2. Recommendation usefulness:
   - Ty le prompt co it nhat 1 goi y hop ly (con hang, dung category) tren bo prompt recommendation.
   - Muc tieu de nghi: >= 80%.
3. Response latency:
   - Thoi gian phan hoi trung binh chatbot.
   - Muc tieu de nghi: <= 6 giay o moi truong demo local.
4. Fallback robustness:
   - Khi LLM loi, chatbot van tra loi duoc bang rule-based/fallback.
   - Muc tieu de nghi: 100% co thong diep fallback hop le.

**Goi y LLM API free-tier cho demo**
1. Google AI Studio (Gemini): thuong co free tier de test nhanh, ho tro tot cho prompt Viet-Anh.
2. Groq Cloud: free dev tier cho model open-source, toc do nhanh de demo.
3. OpenRouter: co mot so model free/community, tien cho demo nhanh nhieu model.
4. Hugging Face Inference: co free credits/muc gioi han nhat dinh cho test.

Luu y: free tier thay doi theo thoi diem va khu vuc, can check quota/throttling ngay luc dang ky.

**Decisions**
- Bao gom:
  - Chatbot tu van + recommend san pham tuong tu
  - Tich hop tren customer portal
  - Song ngu Viet-Anh muc demo
- Khong bao gom:
  - Train deep learning model
  - Vector pipeline phuc tap/ha tang nang
  - Mo rong full production monitoring

**Phan chua ro can ban xac nhan nhanh truoc luc code**
1. Ban muon uu tien provider nao truoc: Tôi sẽ sử dụng API của Google AI Studio
2. Ban muon chatbot dat o dashboard hay hien ca dashboard + product detail? Tôi muốn hiện ở cả dashboard và cả product detail. 
3. Ban co chap nhan recommendation rule-based cho demo (khong deep learning) khong? Tôi chấp nhận recommendation rule-based cho demo (không deep learning).
