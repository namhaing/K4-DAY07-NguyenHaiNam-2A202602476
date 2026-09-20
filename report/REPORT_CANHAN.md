# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Nguyễn Hải Nam
**Nhóm:** G
**Ngày:** 20/09/2026

> **Nộp 1 bản / sinh viên.** Phần nhóm (lựa chọn tài liệu, thiết kế chiến lược, bộ câu hỏi đánh giá, demo) nộp chung 1 bản trong `REPORT_NHOM.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) + Kết quả truy xuất của tôi (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### Độ tương tự Cosine (Cosine Similarity) (Bài tập 1.1)

**Độ tương tự cosine cao (High cosine similarity) nghĩa là gì?**
Khi hai đoạn văn bản có độ tương tự cosine cao, các vector embedding của chúng có cùng hướng hoặc rất gần nhau. Điều đó cho thấy hai đoạn văn bản có nội dung hoặc ý nghĩa tương đồng, dù cách dùng từ có thể khác nhau.

**Ví dụ có độ tương tự CAO:**
- Câu A: Người mua có thể gửi yêu cầu trả hàng nếu sản phẩm nhận được không đúng mô tả.
- Câu B: Khách hàng được phép đề nghị hoàn trả khi món hàng giao tới khác với thông tin đã cam kết.
- Tại sao tương đồng: Hai câu dùng từ vựng khác nhau (`người mua/khách hàng`, `trả hàng/hoàn trả`, `không đúng mô tả/khác thông tin cam kết`) nhưng cùng diễn đạt một ý: khách hàng có quyền yêu cầu trả hàng khi sản phẩm nhận được không khớp mô tả.

**Ví dụ có độ tương tự THẤP:**
- Câu A: Sản phẩm bị lỗi kỹ thuật do nhà sản xuất có thể được bảo hành miễn phí nếu đáp ứng đủ các điều kiện bảo hành.
- Câu B: Người Bán vi phạm có thể bị Shopee hủy tất cả đơn hàng vi phạm.
- Tại sao khác: Câu A nói về điều kiện bảo hành sản phẩm cho Người Mua, còn câu B nói về biện pháp xử lý vi phạm của Người Bán. Hai câu thuộc các chủ đề và đối tượng retrieval khác nhau trong corpus Shopee.

**Tại sao độ tương tự cosine (cosine similarity) được ưu tiên hơn khoảng cách Euclid (Euclidean distance) cho text embeddings?**
Độ tương tự cosine tập trung vào hướng của vector, tức là mối quan hệ về ý nghĩa, và ít bị ảnh hưởng bởi độ dài hoặc độ lớn tuyệt đối của văn bản. Vì vậy, nó thường phù hợp hơn khoảng cách Euclid khi so sánh text embeddings có độ dài khác nhau.

### Bài toán tính toán Chunking (Bài tập 1.2)

**Tài liệu 10,000 ký tự, chunk_size=500, overlap=50. Bao nhiêu chunks?**
Mỗi chunk mới bắt đầu cách chunk trước `chunk_size - overlap = 500 - 50 = 450` ký tự. Vì vậy:

`ceil((10,000 - 50) / (500 - 50)) = ceil(9,950 / 450) = ceil(22.11...) = 23`

> **Đáp án: 23 chunks.**

Kiểm lại bằng `FixedSizeChunker` trong repo:

```bash
python -c "from src.chunking import FixedSizeChunker; print(len(FixedSizeChunker(chunk_size=500, overlap=50).chunk('a'*10000)))"
```

Kết quả thực tế: `23`.

**Nếu độ chồng chéo (overlap) tăng lên 100, số lượng chunk thay đổi thế nào? Tại sao muốn độ chồng chéo nhiều hơn?**
Khi `overlap=100`, bước dịch là `500 - 100 = 400` ký tự, nên số chunk là `ceil((10,000 - 100) / (500 - 100)) = ceil(9,900 / 400) = 25` chunks. Overlap lớn hơn giúp giữ lại nhiều ngữ cảnh ở ranh giới giữa hai chunk, nhờ đó thông tin hoặc câu bị chia đôi vẫn dễ được truy xuất đầy đủ hơn, nhưng sẽ làm tăng số chunk và chi phí xử lý.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

Giải thích cách tiếp cận của bạn khi lập trình (implement) các phần chính trong gói `src`.

### Các hàm chia nhỏ (Chunking Functions)

**`SentenceChunker.chunk`** — hướng tiếp cận:
Tôi dùng regex `re.split(r"(?<=[.!?])\s+", text)` để tách tại vị trí ngay sau dấu kết câu nhưng vẫn giữ lại dấu `.`, `!`, `?` trong câu. Sau đó tôi `.strip()` từng câu, bỏ phần tử rỗng, rồi gom mỗi `max_sentences_per_chunk` câu thành một chunk. Edge case đã xử lý là text rỗng hoặc toàn khoảng trắng trả `[]`; edge case chưa xử lý tốt là chữ viết tắt như `TS.`, `v.v.` và số thập phân có thể bị cắt sai.

**`RecursiveChunker.chunk` / `_split`** — hướng tiếp cận:
Tôi thử separator theo thứ tự từ ranh giới lớn đến nhỏ: đoạn văn, dòng, câu, từ, rồi cuối cùng là cắt cứng theo ký tự. Nếu một mảnh vẫn dài hơn `chunk_size`, `_split` gọi đệ quy với các separator còn lại; sau khi có các mảnh nhỏ, tôi gom các mảnh liền kề lại cho tới khi gần đạt `chunk_size` để tránh tạo nhiều chunk quá vụn. Base case là text rỗng trả `[]`, text đã đủ ngắn trả `[text]`, và khi hết separator hoặc gặp separator rỗng thì fallback sang cắt cứng theo `chunk_size`.

### Lớp EmbeddingStore

**`add_documents` + `search`** — hướng tiếp cận:
Tôi bỏ nhánh ChromaDB và dùng in-memory store để kết quả ổn định trong môi trường test. Mỗi `Document` được chuẩn hoá thành record gồm `id`, `content`, `embedding`, `metadata`; metadata được copy và luôn có `doc_id` để truy vết/xoá theo tài liệu gốc. Khi search, tôi embed query rồi tính dot product với embedding đã chuẩn hoá của từng record, tương đương cosine similarity, sau đó sắp xếp giảm dần theo `score`.

**`search_with_filter` + `delete_document`** — hướng tiếp cận:
Tôi lọc metadata trước rồi mới search trên tập ứng viên đã lọc, vì nếu lấy top-k trước rồi mới lọc thì các slot top-k có thể bị tài liệu sai chiếm hết. `search_with_filter(None)` đi qua cùng helper `_search_records` như `search()` nên kết quả không bị lệch. `delete_document` xoá mọi record có `metadata["doc_id"]` khớp với doc_id cần xoá và trả `True` nếu kích thước store giảm.

### Tác tử KnowledgeBaseAgent

**`answer`** — hướng tiếp cận:
Agent truy xuất `top_k` chunk từ store, có thể truyền thêm `metadata_filter` để dùng cùng đường `search_with_filter()` như benchmark. Mỗi chunk được đánh số dạng `[1]`, `[2]`, `[3]` kèm nguồn từ metadata, rồi đưa toàn bộ vào prompt. Prompt yêu cầu chỉ dùng ngữ cảnh được cung cấp, nếu không có thông tin thì nói rõ là không tìm thấy, và trích dẫn số nguồn khi trả lời để truy vết được về chunk gốc. Nếu store rỗng hoặc không có kết quả, agent trả thông báo trực tiếp thay vì gọi LLM vô ích.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử (Test Results)

```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
collected 42 items

tests/test_solution.py::TestProjectStructure::test_root_main_entrypoint_exists PASSED
tests/test_solution.py::TestProjectStructure::test_src_package_exists PASSED
tests/test_solution.py::TestClassBasedInterfaces::test_chunker_classes_exist PASSED
tests/test_solution.py::TestClassBasedInterfaces::test_mock_embedder_exists PASSED
tests/test_solution.py::TestFixedSizeChunker::test_chunks_respect_size PASSED
tests/test_solution.py::TestFixedSizeChunker::test_correct_number_of_chunks_no_overlap PASSED
tests/test_solution.py::TestFixedSizeChunker::test_empty_text_returns_empty_list PASSED
tests/test_solution.py::TestFixedSizeChunker::test_no_overlap_no_shared_content PASSED
tests/test_solution.py::TestFixedSizeChunker::test_overlap_creates_shared_content PASSED
tests/test_solution.py::TestFixedSizeChunker::test_returns_list PASSED
tests/test_solution.py::TestFixedSizeChunker::test_single_chunk_if_text_shorter PASSED
tests/test_solution.py::TestSentenceChunker::test_chunks_are_strings PASSED
tests/test_solution.py::TestSentenceChunker::test_respects_max_sentences PASSED
tests/test_solution.py::TestSentenceChunker::test_returns_list PASSED
tests/test_solution.py::TestSentenceChunker::test_single_sentence_max_gives_many_chunks PASSED
tests/test_solution.py::TestRecursiveChunker::test_chunks_within_size_when_possible PASSED
tests/test_solution.py::TestRecursiveChunker::test_empty_separators_falls_back_gracefully PASSED
tests/test_solution.py::TestRecursiveChunker::test_handles_double_newline_separator PASSED
tests/test_solution.py::TestRecursiveChunker::test_returns_list PASSED
tests/test_solution.py::TestEmbeddingStore::test_add_documents_increases_size PASSED
tests/test_solution.py::TestEmbeddingStore::test_add_more_increases_further PASSED
tests/test_solution.py::TestEmbeddingStore::test_initial_size_is_zero PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_content_key PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_results_have_score_key PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_results_sorted_by_score_descending PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_returns_at_most_top_k PASSED
tests/test_solution.py::TestEmbeddingStore::test_search_returns_list PASSED
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_non_empty PASSED
tests/test_solution.py::TestKnowledgeBaseAgent::test_answer_returns_string PASSED
tests/test_solution.py::TestComputeSimilarity::test_identical_vectors_return_1 PASSED
tests/test_solution.py::TestComputeSimilarity::test_opposite_vectors_return_minus_1 PASSED
tests/test_solution.py::TestComputeSimilarity::test_orthogonal_vectors_return_0 PASSED
tests/test_solution.py::TestComputeSimilarity::test_zero_vector_returns_0 PASSED
tests/test_solution.py::TestCompareChunkingStrategies::test_counts_are_positive PASSED
tests/test_solution.py::TestCompareChunkingStrategies::test_each_strategy_has_count_and_avg_length PASSED
tests/test_solution.py::TestCompareChunkingStrategies::test_returns_three_strategies PASSED
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_filter_by_department PASSED
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_no_filter_returns_all_candidates PASSED
tests/test_solution.py::TestEmbeddingStoreSearchWithFilter::test_returns_at_most_top_k PASSED
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_reduces_collection_size PASSED
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_false_for_nonexistent_doc PASSED
tests/test_solution.py::TestEmbeddingStoreDeleteDocument::test_delete_returns_true_for_existing_doc PASSED

======================== 42 passed, 1 warning in 0.09s ========================
```

**Số lượng bài test vượt qua (pass):** 42 / 42

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

| Cặp | Câu A | Câu B | Dự đoán | Điểm thực tế | Đúng? |
|------|-----------|-----------|---------|--------------|-------|
| 1 | Người mua có thể yêu cầu trả hàng nếu sản phẩm không đúng mô tả. | Khách hàng được phép hoàn trả khi món hàng nhận được khác thông tin đã cam kết. | Cao nhất — hạng 1 | +0.6502 — hạng 2 | Sai nhẹ |
| 2 | Người mua có 15 ngày để gửi yêu cầu trả hàng hoặc hoàn tiền. | Người bán cần phản hồi yêu cầu trả hàng trong vòng 02 ngày lịch. | Cao — hạng 2 | +0.6919 — hạng 1 | Sai nhẹ |
| 3 | Sản phẩm lỗi kỹ thuật do nhà sản xuất có thể được bảo hành miễn phí. | Hàng hóa còn hạn sử dụng phải còn ít nhất 30 phần trăm thời hạn sử dụng. | Thấp — hạng 4 | +0.3880 — hạng 4 | Đúng |
| 4 | Shopee sẽ hoàn tiền sau khi yêu cầu trả hàng được chấp nhận. | Shopee có thể xử lý người bán vi phạm bằng cách hạn chế tài khoản. | Trung bình — hạng 3 | +0.6280 — hạng 3 | Đúng |
| 5 | Chính sách bảo hành áp dụng cho sản phẩm mua tại Shopee. | Bưu cục nhận hàng hoàn trả theo phương thức gửi hàng của người mua. | Thấp nhất — hạng 5 | +0.3831 — hạng 5 | Đúng |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**
Cặp 2 bất ngờ nhất vì tôi dự đoán cặp 1 sẽ cao nhất: cặp 1 gần nghĩa hơn về mặt diễn đạt, nhưng cặp 2 lại có nhiều tín hiệu cùng miền như `trả hàng`, `hoàn tiền`, `ngày`, `yêu cầu`. Điều này cho thấy embedding không chỉ nhìn quan hệ đồng nghĩa, mà còn gom mạnh các câu cùng trường chủ đề/chính sách, kể cả khi đáp án khác đối tượng buyer/seller. Đây cũng là lý do metadata filter quan trọng: semantic similarity cao chưa chắc đã đúng audience.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Chạy **5 câu hỏi đánh giá của nhóm** trên mã nguồn cá nhân của bạn trong gói `src`. **5 câu hỏi này phải trùng với các thành viên cùng nhóm** (xem `REPORT_NHOM.md`).

**Cấu hình:** `ClauseChunker(max_chars=400)` · embedding `text-embedding-3-small` · 491 chunk từ 9 tài liệu · agent dùng `gpt-4o-mini`.

| # | Câu hỏi (Query) | Top-1 Chunk truy xuất được (tóm tắt) | Điểm Score | Có liên quan không? | Câu trả lời của Agent (tóm tắt) |
|---|-------|--------------------------------|-------|-----------|------------------------|
| 1 | Bảo hành sản phẩm thông qua Shopee mất bao lâu? | `bao-hanh-san-pham` — mục 4 "Bảo hành thông qua Shopee" | +0.7253 | Có | "từ **20 ngày đến 45 ngày làm việc** tính từ lúc Shopee nhận được sản phẩm" — **đúng** |
| 2 | Sản phẩm cần thỏa điều kiện gì để được bảo hành miễn phí? | `bao-hanh-san-pham` — "1. ĐIỀU KIỆN BẢO HÀNH" | +0.6246 | Có | Liệt kê đủ 4 điều kiện: lỗi kỹ thuật do NSX, còn thời hạn BH, có hóa đơn/mã đơn, tem nguyên vẹn — **đúng** |
| 3 | Thời hạn gửi yêu cầu Trả hàng/Hoàn tiền với từng loại đơn hàng? | `tra-hang-hoan-tien-nguoi-mua` — Điều 3.2 | +0.7332 | Có | "**15 ngày** với đơn thường, **24 giờ** với thực phẩm tươi sống" — **đúng nhưng thiếu** mốc 20 ngày |
| 4 | Người bán được đăng bán hàng còn bao nhiêu hạn sử dụng? | `quy-dinh-dang-ban-san-pham` — điểm a | +0.6265 | Có | "còn ít nhất **30% thời hạn sử dụng** và ít nhất **30 ngày**" — **đúng** |
| 5 | Bên liên quan có bao nhiêu ngày để xử lý yêu cầu trả hàng/hoàn tiền? *(cần filter)* | `tra-hang-hoan-tien-nguoi-mua` — Điều 3.2 | +0.6289 | Có | Trước khi sửa agent trả lời "**6 ngày**" sai nguồn; đã sửa `answer()` để nhận `metadata_filter` và dùng `search_with_filter()` |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** **5** / 5

### Chấm hai mức — chênh lệch là phát hiện đáng giá nhất

| # | Chấm theo `doc_id` | Chấm theo nội dung | Ghi chú |
|---|---|---|---|
| 1 | 2/2 | 1/2 | chênh |
| 2 | 2/2 | 2/2 | |
| 3 | 1/2 | 0/2 | chênh — ngữ cảnh thiếu chuỗi `15 ngày` |
| 4 | 2/2 | 2/2 | |
| 5 | 2/2 | 2/2 | |
| **Tổng** | **9/10** | **7/10** | |

Cách chấm ngây thơ (chỉ kiểm `doc_id` gold có trong top-3) cho **9/10**, nhưng chấm đúng theo `docs/SCORING.md` — đòi ngữ cảnh truy xuất được phải **chứa chuỗi đáp án** — chỉ còn **7/10**. Chênh 2 điểm ở câu 1 và câu 3: retrieval lấy đúng tài liệu nhưng chunk lọt top-3 không phải chunk chứa con số.

### A/B metadata filter (câu 5)

| Lần chạy | `audience` của top-3 | Chuỗi đáp án trong ngữ cảnh |
|---|---|---|
| Không filter | `buyer, buyer, seller` | chỉ `15 (mười lăm) ngày` |
| `{"audience": "buyer"}` | `buyer, buyer, buyer` | `15 (mười lăm) ngày` |
| `{"audience": "seller"}` | `seller, seller, seller` | `02 ngày lịch` |

Không lọc thì top-3 **lẫn cả hai đối tượng** — chunk người mua (15 ngày) và chunk người bán (02 ngày lịch) cùng xuất hiện. Lọc xong mỗi bên trả về đúng đáp án của mình. Đây là bằng chứng metadata filter có tác dụng thật.

### Phân tích lỗi (Failure analysis)

**Lỗi 1 — câu 5: agent trả lời sai đối tượng, dù retrieval đúng.**

Trước khi sửa, agent trả lời *"6 ngày, theo Điều khoản Dịch vụ Shopee Mall"* — sai cả con số lẫn nguồn. Nguyên nhân nằm ở `src/agent.py`: `KnowledgeBaseAgent.answer()` gọi `self.store.search()`, **không phải** `search_with_filter()`. Nghĩa là dù `bench.py` lọc `audience=buyer` để chấm retrieval, agent vẫn sinh câu trả lời từ ngữ cảnh **chưa lọc**, trong đó có tài liệu dành cho người bán.

*Đã sửa:* thêm tham số `metadata_filter` vào `answer()` và truyền xuống `search_with_filter()`. Retrieval sạch mà agent vẫn đọc dữ liệu bẩn thì lọc metadata không có tác dụng ở đầu ra, nên tầng agent cũng phải dùng cùng bộ lọc với tầng đánh giá.

**Lỗi 2 — câu 3: chunk nhỏ làm vỡ câu hỏi dạng liệt kê.**

Câu 3 hỏi thời hạn cho **từng loại** đơn hàng, đáp án gồm ba mốc: 15 ngày (đơn thường), 24 giờ (thực phẩm tươi sống), 20 ngày (chưa bấm đã nhận hàng). `ClauseChunker` tách mỗi khoản thành một chunk riêng nên ba mốc nằm ở ba chunk khác nhau, và chỉ một phần lọt được top-3 — điểm nội dung 0/2.

Đây là **mặt trái của chính chiến lược tôi chọn**: chunk nhỏ làm tăng mật độ đáp án cho câu hỏi tra một con số (câu 1, 4, 5 đều 2/2), nhưng làm hỏng câu hỏi cần gom nhiều mảnh thông tin. `HeadingChunker` của Hiền gộp cả mục nên nhiều khả năng thắng ở câu này.

*Đề xuất sửa:* tăng `max_chars` hoặc cho `ClauseChunker` gộp các khoản cùng một Điều khi tổng vẫn dưới ngưỡng, để một câu hỏi liệt kê vẫn lấy được trọn cụm.

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**
Tôi học được từ chiến lược theo heading rằng không phải lúc nào chunk nhỏ cũng tốt: với câu hỏi cần nhiều mốc thời gian trong cùng một mục, giữ nguyên section có thể giúp agent thấy bức tranh đầy đủ hơn. Ngược lại, fixed-size của Duy là baseline rất hữu ích vì nó cho thấy lợi ích/thất bại của các chiến lược có hiểu cấu trúc. So sánh trong nhóm làm rõ rằng chunking là một quyết định đánh đổi giữa mật độ đáp án và độ mạch lạc của ngữ cảnh.

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí | Điểm tự đánh giá |
|----------|-------------------|
| Khởi động (Warm-up) | 5 / 5 |
| Hướng tiếp cận của tôi (My Approach) | 10 / 10 |
| Hoàn thiện code (Core Implementation — tests) | 30 / 30 |
| Dự đoán độ tương tự (Similarity Predictions) | 5 / 5 |
| Kết quả truy xuất của tôi (Competition Results) | 9 / 10 |
| **Tổng phần cá nhân** | **59 / 60** |
