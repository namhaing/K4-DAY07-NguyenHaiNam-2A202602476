# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** G
**Thành viên:** Duy, Nguyễn Hải Nam, Hiền, Tâm
**Ngày:** 2026-09-20

> **Nộp 1 bản / nhóm.** Phần cá nhân (hướng tiếp cận, kết quả riêng, dự đoán…) mỗi thành viên nộp riêng trong `REPORT_CANHAN.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần nhóm: 40** = Lựa chọn tài liệu (10) + Thiết kế chiến lược (15) + Chất lượng truy xuất (10) + Thuyết trình (5).

---

## 1. Lựa chọn tài liệu (Document Set Quality) — Nhóm (10 điểm)

### Chủ đề (Domain) & Lý Do Chọn

**Chủ đề:** Chính sách hỗ trợ và quy định vận hành trên Shopee: bảo hành, trả hàng/hoàn tiền, quy định đăng bán và điều khoản liên quan.

**Tại sao nhóm chọn chủ đề này?**
Nhóm chọn bộ tài liệu này vì nội dung có nhiều điều kiện, thời hạn và quy trình cụ thể, phù hợp để đánh giá retrieval theo chunk. Các chính sách Shopee cũng có metadata tự nhiên như `audience`, `category`, `document_version`, giúp kiểm tra rõ tác dụng của `search_with_filter`. Đặc biệt, cùng một chủ đề trả hàng/hoàn tiền có nội dung khác nhau cho Người Mua và Người Bán, nên có thể thiết kế câu hỏi bắt buộc cần lọc metadata.

### Danh sách tài liệu (Data Inventory)

| # | Tên tài liệu | Nguồn (Source URL) | Ngày lấy / Phiên bản | Số ký tự | Metadata đã gán |
|---|--------------|------------|--------------------|----------|-----------------|
| 1 | Chính sách bảo hành cho sản phẩm mua tại Shopee | Shopee Help Center | 2026-09-20 / not-stated | 3,201 | `audience=buyer`, `category=warranty-policy`, `language=vi` |
| 2 | Chính sách Trả hàng và Hoàn tiền (Người Mua) | Shopee Help Center | 2026-09-20 / hieu-luc-2026-03-11 | 15,549 | `audience=buyer`, `category=returns-policy`, `language=vi` |
| 3 | Chính sách Trả hàng và Hoàn tiền (Người Bán) | Shopee Help Center | 2026-09-20 / hieu-luc-2026-03-11 | 7,752 | `audience=seller`, `category=returns-policy`, `language=vi` |
| 4 | Những quy định chung về Trả hàng/Hoàn tiền của Shopee | Shopee Help Center | 2026-09-20 / not-stated | 6,047 | `audience=buyer`, `category=returns-policy`, `language=vi` |
| 5 | Các phương thức gửi hàng hoàn trả và phí hoàn trả | Shopee Help Center | 2026-09-20 / not-stated | 5,651 | `audience=buyer`, `category=returns-policy`, `language=vi` |
| 6 | Quy định về đăng bán sản phẩm trên Shopee | Shopee Help Center | 2026-09-20 / hieu-luc-2024-08-21 | 21,316 | `audience=seller`, `category=seller-regulations`, `language=vi` |
| 7 | Chính sách chống hành vi gian lận và xử lý Người Bán vi phạm | Shopee Help Center | 2026-09-20 / hieu-luc-2023-12-28 | 6,242 | `audience=seller`, `category=seller-regulations`, `language=vi` |
| 8 | Điều khoản Dịch vụ của Shopee Mall | Shopee Help Center | 2026-09-20 / hieu-luc-2026-05-08 | 25,673 | `audience=seller`, `category=seller-regulations`, `language=vi` |
| 9 | Quy chế hoạt động Sàn TMĐT Shopee.vn | Shopee Help Center | 2026-09-20 / hieu-luc-2025-01-10 | 9,595 | `audience=both`, `category=platform-terms`, `language=vi` |

**Danh sách kiểm tra quản trị dữ liệu (Data governance checklist):**
- [x] Tập tài liệu (Corpus) chỉ chứa nguồn công khai/được phép dùng và không chứa dữ liệu cá nhân, thông tin đăng nhập hoặc tài liệu nội bộ.
- [x] Mỗi tài liệu có `source_url`, `retrieved_at`, `document_version` (hoặc ngày hiệu lực) trong metadata.

### Cấu trúc Metadata (Metadata Schema)

| Trường metadata | Kiểu | Ví dụ giá trị | Tại sao hữu ích cho truy xuất (retrieval)? |
|----------------|------|---------------|-------------------------------|
| `doc_id` | string | `shopee-chinh-sach-tra-hang-hoan-tien-nguoi-mua` | Truy vết chunk về file gốc và dùng cho gold answer/delete. |
| `source_url` | string | `https://help.shopee.vn/...` | Cho biết nguồn công khai để kiểm chứng lại câu trả lời. |
| `retrieved_at` | date string | `2026-09-20` | Giúp biết tài liệu được lấy ở thời điểm nào, quan trọng với chính sách có thể thay đổi. |
| `document_version` | string | `hieu-luc-2026-03-11` | Phân biệt phiên bản chính sách/hiệu lực khi nội dung thay đổi. |
| `audience` | enum string | `buyer`, `seller`, `both` | Dùng cho câu hỏi cần lọc theo đối tượng Người Mua/Người Bán. |
| `category` | enum string | `returns-policy`, `warranty-policy` | Giúp lọc theo nhóm nghiệp vụ và phân tích lỗi retrieval. |
| `language` | string | `vi` | Đánh dấu corpus tiếng Việt để chọn embedding model phù hợp. |

---

## 2. Thiết kế chiến lược (Strategy Design) — Nhóm (15 điểm)

> Mỗi thành viên thử **một chiến lược khác nhau** trên cùng bộ tài liệu; nhóm tổng hợp và so sánh ở đây.

### Phân tích đường cơ sở (Baseline Analysis)

Chạy `ChunkingStrategyComparator().compare()` trên 2-3 tài liệu:

| Tài liệu | Chiến lược (Strategy) | Số lượng Chunk | Độ dài trung bình | Giữ được ngữ cảnh không? |
|-----------|----------|-------------|------------|-------------------|
| `shopee-chinh-sach-bao-hanh-san-pham.md` | FixedSizeChunker (`fixed_size`) | 10 | 365.1 | Trung bình; có overlap nhưng có thể cắt ngang điều kiện. |
| `shopee-chinh-sach-bao-hanh-san-pham.md` | SentenceChunker (`by_sentences`) | 5 | 637.6 | Giữ câu tốt nhưng chunk hơi dài, nhiều ý bị gộp. |
| `shopee-chinh-sach-bao-hanh-san-pham.md` | RecursiveChunker (`recursive`) | 10 | 313.8 | Tốt hơn fixed vì ưu tiên ranh giới tự nhiên. |
| `shopee-chinh-sach-tra-hang-hoan-tien-nguoi-mua.md` | FixedSizeChunker (`fixed_size`) | 45 | 394.4 | Ổn định về kích thước nhưng có thể mất ranh giới điều khoản. |
| `shopee-chinh-sach-tra-hang-hoan-tien-nguoi-mua.md` | SentenceChunker (`by_sentences`) | 40 | 386.7 | Giữ câu, nhưng không biết cấu trúc điều/khoản. |
| `shopee-chinh-sach-tra-hang-hoan-tien-nguoi-mua.md` | RecursiveChunker (`recursive`) | 52 | 296.5 | Nhiều chunk gọn hơn, hợp với retrieval theo điều kiện/thời hạn. |
| `shopee-quy-dinh-dang-ban-san-pham.md` | FixedSizeChunker (`fixed_size`) | 61 | 398.6 | Kích thước đều, phù hợp baseline. |
| `shopee-quy-dinh-dang-ban-san-pham.md` | SentenceChunker (`by_sentences`) | 78 | 270.5 | Nhiều chunk nhỏ, đôi khi tách rời heading và nội dung. |
| `shopee-quy-dinh-dang-ban-san-pham.md` | RecursiveChunker (`recursive`) | 66 | 318.2 | Cân bằng hơn giữa kích thước và ranh giới văn bản. |

### Chiến lược của từng thành viên

> Mỗi thành viên điền một khối dưới đây (copy thêm nếu nhóm có nhiều hơn 3 người).

**Thành viên 1 — Duy**
- **Loại chiến lược:** FixedSizeChunker (`chunk_size=500`, `overlap=50`)
- **Mô tả & lý do chọn cho chủ đề này:** Đây là baseline đơn giản, không phụ thuộc cấu trúc văn bản. Overlap giúp giảm rủi ro một câu hoặc một điều khoản bị cắt đúng ranh giới chunk.
- **Code snippet (nếu custom):**
```python
CHUNKER = FixedSizeChunker(chunk_size=500, overlap=50)
```

**Thành viên 2 — Tâm**
- **Loại chiến lược:** RecursiveChunker (`chunk_size=400`)
- **Mô tả & lý do chọn:** Chiến lược này ưu tiên ranh giới tự nhiên như đoạn, dòng, câu rồi mới cắt nhỏ hơn. Nó không hiểu heading/điều khoản, nhưng thường ít làm vỡ câu hơn fixed-size.
- **Code snippet (nếu custom):**
```python
CHUNKER = RecursiveChunker(chunk_size=400)
```

**Thành viên 3 — Hiền**
- **Loại chiến lược:** Custom `HeadingChunker(max_chars=800)`
- **Mô tả & lý do chọn:** Văn bản chính sách thường được chia theo heading/mục, nên mỗi section là một đơn vị ngữ nghĩa tương đối hoàn chỉnh. Nếu section quá dài, chunker hạ xuống `RecursiveChunker` và gắn lại heading vào từng mảnh con để không mất ngữ cảnh.
- **Code snippet (nếu custom):**
```python
CHUNKER = HeadingChunker(max_chars=800)
```

**Thành viên 4 — Nguyễn Hải Nam**
- **Loại chiến lược:** Custom `ClauseChunker(max_chars=400)`
- **Mô tả & lý do chọn:** `ClauseChunker` tách nhỏ hơn heading một bậc, theo điều/khoản/điểm như `1.`, `1.1.`, `a.`, `ii.`. Cách này phù hợp vì benchmark có nhiều câu hỏi hỏi số ngày, điều kiện hoặc quy trình nằm trong một khoản cụ thể; chunk nhỏ hơn giúp tăng mật độ đáp án.
- **Code snippet (nếu custom):**
```python
CHUNKER = ClauseChunker(max_chars=400)
```

### So Sánh Giữa Các Thành Viên

> **Nguồn số liệu:** bảng dưới lấy từ một lần chạy đối chứng do **Nam** thực hiện
> (`python bench.py --all-strategies`, kết quả đầy đủ trong `so_sanh_4_chien_luoc.txt`), dùng
> **cùng embedder `text-embedding-3-small`, cùng corpus 9 tài liệu và cùng bộ 5 benchmark query**.
> Đây là phép đo đối chứng chung để so sánh công bằng giữa bốn chiến lược; nếu mỗi người dùng
> một embedder khác nhau thì bảng không còn đo chiến lược chunking nữa (xem ghi chú bên dưới).

| Thành viên | Chiến lược (Strategy) | Số chunk | Avg length | Doc-id (/10) | **Nội dung (/10)** | Điểm mạnh | Điểm yếu |
|-----------|----------|---:|---:|---:|---:|-----------|----------|
| Duy | `FixedSizeChunker(500, 50)` | 229 | 489,2 | 8 | **5** | Kích thước đều, overlap giữ được thông tin vắt qua ranh giới | Cắt ngang điều khoản; chunk to nhưng nội dung trộn nhiều ý không liên quan |
| Tâm | `RecursiveChunker(400)` | 325 | 307,2 | 9 | **7** | Tôn trọng ranh giới tự nhiên, ít vỡ câu | Không biết cấu trúc Điều/Khoản nên vẫn tách nhầm chỗ |
| Hiền | `HeadingChunker(800)` | 167 | 642,4 | 8 | **9**  | Mỗi mục là một đơn vị ngữ nghĩa trọn vẹn, chunk luôn kèm đáp án | Ít chunk nhất, các section cùng tài liệu cạnh tranh điểm gần nhau |
| Nam | `ClauseChunker(400)` | 491 | 250,6 | 9 | **7** | Mật độ đáp án cao, thắng câu hỏi tra một con số | Tách đáp án liệt kê thành nhiều chunk; phụ thuộc regex đánh số |

> **Ghi chú phương pháp — embedding backend phải thống nhất.** Nhóm đo được rằng cùng
> `ClauseChunker`, cùng corpus, cùng 5 câu, nhưng chạy bằng `MockEmbedder` cho **0/10** còn
> `text-embedding-3-small` cho **7/10**. Chênh 7 điểm mà không đổi một dòng chiến lược nào.
> Vì vậy mọi số trong bảng trên đều dùng chung một embedder; nếu không, bảng sẽ đo
> "ai có API key" thay vì đo chiến lược chunking.

**Chiến lược nào tốt nhất cho chủ đề này? Tại sao?**

`HeadingChunker` thắng với **9/10**, và kết quả này **bác bỏ giả thuyết ban đầu của nhóm** rằng
chunk càng nhỏ càng tốt vì "mật độ đáp án cao hơn" — `ClauseChunker` chia nhỏ gấp 3 lần
(491 so với 167 chunk) nhưng chỉ được 7/10.

Lý do nhìn thấy được khi tách hai mức chấm: điểm theo `doc_id` của cả bốn chiến lược gần như
nhau (8–9/10), nghĩa là **ai cũng lấy đúng tài liệu**. Khác biệt nằm ở chỗ chunk lọt top-3 có
**chứa con số đáp án** hay không. Văn bản chính sách Shopee được người soạn chia sẵn theo mục,
mỗi mục đã là một đơn vị trả lời trọn vẹn; cắt nhỏ hơn mức đó sẽ tách con số ra khỏi điều kiện
đi kèm nó. Câu 3 minh hoạ rõ nhất: đáp án gồm ba mốc (15 ngày / 24 giờ / 20 ngày) nằm ở ba khoản
khác nhau, `ClauseChunker` đẩy chúng thành ba chunk riêng và chỉ một chunk lọt top-3.

Kết luận nhóm rút ra: **đơn vị chunk nên khớp với đơn vị trả lời của văn bản, không phải càng
nhỏ càng tốt.** Với văn bản có cấu trúc mục rõ ràng thì heading là mức đúng; `ClauseChunker` sẽ
hợp hơn nếu benchmark toàn câu hỏi tra một con số đơn lẻ — nó thắng ở các câu 1, 4, 5 nhưng
mất trắng ở câu hỏi dạng liệt kê.

---

## 3. Câu hỏi đánh giá & Chất lượng truy xuất (Retrieval Quality) — Nhóm (10 điểm)

### Câu hỏi đánh giá & Câu trả lời chuẩn (nhóm thống nhất)

> **Đúng 5 câu hỏi**, đa dạng, có thể kiểm chứng; **ít nhất 1 câu** cần lọc metadata mới trả lời tốt. Đây là bộ câu hỏi chung cho mọi thành viên chạy.

| # | Câu hỏi (Query) | Câu trả lời chuẩn (Gold Answer) | Chunk nào chứa thông tin? |
|---|-------|-------------------------------|--------------------------|
| 1 | Bảo hành sản phẩm thông qua Shopee mất bao lâu? | "Thời gian bảo hành sản phẩm của quý khách dự kiến từ **20 ngày đến 45 ngày làm việc** tính từ lúc Shopee nhận được sản phẩm" | `shopee-chinh-sach-bao-hanh-san-pham.md` — mục 4.b "Bảo hành thông qua Shopee" |
| 2 | Sản phẩm cần thỏa những điều kiện gì để được bảo hành miễn phí? | 4 điều kiện: "Sản phẩm bị **lỗi kỹ thuật do nhà sản xuất**"; "**Còn trong thời hạn bảo hành**"; "Có **hóa đơn điện tử**... hoặc **mã đơn hàng**"; phiếu/tem bảo hành "**còn nguyên vẹn**" (điện gia dụng) | `shopee-chinh-sach-bao-hanh-san-pham.md` — mục 1 "ĐIỀU KIỆN BẢO HÀNH" |
| 3 | Thời hạn gửi yêu cầu Trả hàng/Hoàn tiền với từng loại đơn hàng là bao lâu? | Đơn hàng thường: "**15 ngày** kể từ lúc đơn hàng được cập nhật trạng thái 'Giao hàng thành công'"; thực phẩm tươi sống & đông lạnh: "trong vòng **24 giờ**"; chưa bấm 'Đã nhận được hàng': "**20 ngày** kể từ lúc đơn hàng được cập nhật trạng thái 'Lấy hàng thành công'" | `shopee-quy-dinh-chung-tra-hang-hoan-tien.md` — bảng thời hạn |
| 4 | Người bán được đăng bán hàng hóa còn bao nhiêu hạn sử dụng? | "phải còn ít nhất **30% thời hạn sử dụng** và còn ít nhất **30 ngày**, tính từ thời điểm hiện tại đến ngày hết hạn" | `shopee-quy-dinh-dang-ban-san-pham.md` — quy định hạn sử dụng |
| 5 | **Bên liên quan có bao nhiêu ngày để xử lý yêu cầu trả hàng/hoàn tiền?** *(cần `metadata_filter`)* | `audience=buyer` → "Người Mua có thể gửi yêu cầu trả hàng/hoàn tiền trong vòng **15 (mười lăm) ngày**"<br>`audience=seller` → "Người Bán cần gửi phản hồi trong vòng **02 ngày lịch**" | `shopee-chinh-sach-tra-hang-hoan-tien-nguoi-mua.md` (Điều 3.2) và `...-nguoi-ban.md` (Điều 5) |

Ghi chú: Câu 5 được thiết kế để chạy A/B: không filter, `metadata_filter={"audience": "buyer"}` và `metadata_filter={"audience": "seller"}`. Hai file buyer/seller đã được tách riêng, file gốc gộp hai đối tượng không còn nằm trong corpus benchmark. Với một số chiến lược như `ClauseChunker`, không filter làm top-3 lẫn cả buyer và seller; khi lọc theo audience, ngữ cảnh được ép về đúng đối tượng và lần lượt chứa `15 (mười lăm) ngày` hoặc `02 ngày lịch`.

### Tổng hợp chất lượng truy xuất của nhóm

> Cách chấm (theo `docs/SCORING.md`): **2 điểm/câu** — top-3 chứa chunk liên quan + agent trả lời đúng (2), có liên quan nhưng thiếu/không ở top-1 (1), không có trong top-3 (0).

| # | Câu hỏi | Chiến lược tốt nhất cho câu này | Có chunk liên quan trong top-3? | Ghi chú |
|---|---------|-------------------------------|-------------------------------|---------|
| 1 | Bảo hành thông qua Shopee mất bao lâu? | `HeadingChunker` | Có ở cả 4 chiến lược; heading đạt 2/2 | Fixed/Recursive/Clause lấy đúng tài liệu nhưng chunk chứa mốc `20 ngày đến 45 ngày` không đứng top-1 nên chỉ 1/2. |
| 2 | Điều kiện bảo hành miễn phí là gì? | `ClauseChunker` | Có, nhưng chỉ Clause đạt 2/2 | Clause đưa đúng khoản "ĐIỀU KIỆN BẢO HÀNH" lên top-1; Fixed/Recursive lấy chunk cùng chủ đề nhưng thiếu chuỗi `lỗi kỹ thuật do nhà sản xuất`. |
| 3 | Thời hạn gửi yêu cầu trả hàng/hoàn tiền theo từng loại đơn? | `RecursiveChunker` và `HeadingChunker` | Có với Recursive/Heading; Fixed/Clause thiếu nội dung | Đây là câu hỏi liệt kê nhiều mốc, nên chunk quá nhỏ dễ tách `15 ngày`, `24 giờ`, `20 ngày` ra nhiều mảnh khác nhau. |
| 4 | Hàng hóa còn bao nhiêu hạn sử dụng mới được đăng bán? | Cả 4 chiến lược | Có ở cả 4 chiến lược | Đây là câu hỏi tra một con số nằm gọn trong một đoạn, nên chiến lược nào cũng lấy được `30% thời hạn sử dụng` trong top-3. |
| 5 | Bên liên quan có bao nhiêu ngày xử lý yêu cầu trả hàng/hoàn tiền? | Cả 4 chiến lược khi có filter buyer | Có ở cả 4 chiến lược | Đây là câu bắt buộc kiểm metadata filter: buyer trả về `15 (mười lăm) ngày`, seller trả về `02 ngày lịch`. |

**Lọc bằng metadata có giúp ích không? Ở câu hỏi nào?**
Metadata filter giúp rõ nhất ở câu 5. Câu hỏi cố tình không nói người hỏi là Người Mua hay Người Bán, trong khi corpus có hai tài liệu cùng chủ đề trả hàng/hoàn tiền nhưng đáp án khác nhau: buyer là `15 (mười lăm) ngày`, seller là `02 ngày lịch`. Không filter thì top-3 có thể lẫn hai audience; filter giúp ép retrieval về đúng đối tượng cần trả lời.

Trong lần chạy đối chứng, cả 4 chiến lược đều báo `A/B filter đổi top-k = có`. Với `ClauseChunker`, bằng chứng rõ nhất: không filter có `buyer, buyer, seller`, filter buyer thành `buyer, buyer, buyer`, filter seller thành `seller, seller, seller`. Điều này cũng phát hiện một bug quan trọng ở tầng agent: nếu `KnowledgeBaseAgent.answer()` vẫn gọi `search()` thay vì `search_with_filter()`, retrieval đã lọc đúng nhưng câu trả lời cuối vẫn có thể sai đối tượng.

---

## 4. Thuyết trình (Demo) & Bài học nhóm — Nhóm (5 điểm)

**Những phân tích (insights) hay nhất nhóm sẽ trình bày:**
- Chấm theo `doc_id` có thể thổi phồng kết quả: lấy đúng tài liệu chưa chắc chunk top-3 chứa chuỗi đáp án.
- Metadata filter có tác dụng thật ở câu 5 vì cùng một chủ đề có hai đáp án khác nhau cho buyer/seller.
- Failure case đáng chú ý: nếu agent dùng `store.search()` thay vì `search_with_filter()`, retrieval đã lọc sạch nhưng câu trả lời cuối vẫn có thể sai đối tượng.

**Bài học rút ra khi so sánh trong nhóm:**
Cùng một corpus nhưng chiến lược chunking làm thay đổi mạnh số lượng chunk và độ mạch lạc của ngữ cảnh. Chunk nhỏ theo điều/khoản tốt cho câu hỏi tra một con số, nhưng dễ làm hỏng câu hỏi cần liệt kê nhiều mốc; chunk theo heading giữ ngữ cảnh tốt hơn nhưng có thể loãng và khiến các section cùng chủ đề cạnh tranh điểm gần nhau.

**Nếu làm lại, nhóm sẽ thay đổi gì trong chiến lược dữ liệu (data strategy)?**
Nhóm sẽ chuẩn hóa sớm metadata `audience`, tách riêng các tài liệu có nhiều đối tượng trả lời, và thêm bộ câu kiểm thử riêng cho filter. Ngoài ra, nhóm sẽ ghi rõ chuỗi đáp án kỳ vọng cho từng query ngay từ đầu để chấm ở mức nội dung thay vì chỉ nhìn `doc_id`.

---

## Tự Đánh Giá (Phần Nhóm)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Lựa chọn tài liệu (Document Set Quality) | 10 / 10 |
| Thiết kế chiến lược (Strategy Design) | 14 / 15 |
| Chất lượng truy xuất (Retrieval Quality) | 9 / 10 |
| Thuyết trình (Demo) | 4 / 5 |
| **Tổng phần nhóm** | **37 / 40** |
