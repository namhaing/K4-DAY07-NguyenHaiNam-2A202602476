"""Bài tập 3.3 — Dự đoán độ tương tự cosine (REPORT_CANHAN mục 4, 5 điểm).

Cách dùng:
  1. Điền 5 cặp câu vào PAIRS bên dưới.
  2. ĐIỀN DỰ ĐOÁN TRƯỚC KHI CHẠY — xếp hạng 5 cặp từ giống nhất đến khác nhất.
     Đây là cả điểm của bài tập: dự đoán sau khi xem kết quả thì không còn ý nghĩa.
  3. python predict_similarity.py

Backend embedding lấy theo .env (EMBEDDING_PROVIDER=gemini|openai|local|mock).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from src import (
    EMBEDDING_PROVIDER_ENV,
    GEMINI_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_MODEL,
    GeminiEmbedder,
    LocalEmbedder,
    OpenAIEmbedder,
    _mock_embed,
    compute_similarity,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 5 cặp câu. Gợi ý: lấy từ corpus Shopee của nhóm cho ăn nhập với bài,
# và trộn đủ loại — gần nghĩa khác chữ, cùng chủ đề khác đối tượng,
# khác chủ đề hẳn, cùng chữ khác nghĩa.
# ---------------------------------------------------------------------------
PAIRS: list[tuple[str, str]] = [
    (
        "Người mua có thể yêu cầu trả hàng nếu sản phẩm không đúng mô tả.",
        "Khách hàng được phép hoàn trả khi món hàng nhận được khác thông tin đã cam kết.",
    ),
    (
        "Người mua có 15 ngày để gửi yêu cầu trả hàng hoặc hoàn tiền.",
        "Người bán cần phản hồi yêu cầu trả hàng trong vòng 02 ngày lịch.",
    ),
    (
        "Sản phẩm lỗi kỹ thuật do nhà sản xuất có thể được bảo hành miễn phí.",
        "Hàng hóa còn hạn sử dụng phải còn ít nhất 30 phần trăm thời hạn sử dụng.",
    ),
    (
        "Shopee sẽ hoàn tiền sau khi yêu cầu trả hàng được chấp nhận.",
        "Shopee có thể xử lý người bán vi phạm bằng cách hạn chế tài khoản.",
    ),
    (
        "Chính sách bảo hành áp dụng cho sản phẩm mua tại Shopee.",
        "Bưu cục nhận hàng hoàn trả theo phương thức gửi hàng của người mua.",
    ),
]

# ---------------------------------------------------------------------------
# DỰ ĐOÁN CỦA TÔI — điền TRƯỚC khi chạy.
# Xếp hạng từ 1 (tương tự CAO nhất) đến 5 (THẤP nhất), theo thứ tự PAIRS ở trên.
# Ví dụ PREDICTED_RANK = [2, 1, 5, 3, 4] nghĩa là cặp 1 xếp hạng 2, cặp 2 xếp hạng 1...
# ---------------------------------------------------------------------------
PREDICTED_RANK: list[int] = [1, 2, 4, 3, 5]


def pick_embedder():
    load_dotenv(override=False)
    provider = os.getenv(EMBEDDING_PROVIDER_ENV, "mock").strip().lower()
    try:
        if provider == "local":
            return LocalEmbedder(model_name=os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        if provider == "openai":
            return OpenAIEmbedder(model_name=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
        if provider == "gemini":
            return GeminiEmbedder(model_name=os.getenv("GEMINI_EMBEDDING_MODEL", GEMINI_EMBEDDING_MODEL))
    except Exception as error:  # noqa: BLE001
        print(f"  ! Không dùng được backend '{provider}' ({error}); rơi về mock.\n")
    return _mock_embed


def main() -> int:
    if any(not a or not b for a, b in PAIRS):
        print("Chưa điền đủ 5 cặp câu vào PAIRS. Mở file và điền trước đã.")
        return 2
    if sorted(PREDICTED_RANK) != [1, 2, 3, 4, 5]:
        print("PREDICTED_RANK phải là một hoán vị của [1,2,3,4,5].")
        print("Điền dự đoán TRƯỚC khi chạy — đó là cả điểm của bài tập 3.3.")
        return 2

    embedder = pick_embedder()
    backend = getattr(embedder, "_backend_name", embedder.__class__.__name__)
    print(f"Embedding backend: {backend}")
    if embedder is _mock_embed:
        print("  ! MockEmbedder băm MD5, KHÔNG mã hoá ngữ nghĩa.")
        print("  ! Mọi điểm số dưới đây là nhiễu ngẫu nhiên — dự đoán của bạn gần như chắc chắn")
        print("  ! sẽ sai, và ĐÓ CHÍNH LÀ phần phản ngẫm cần viết vào báo cáo.\n")

    scores = [compute_similarity(embedder(a), embedder(b)) for a, b in PAIRS]
    actual_rank = {i: r for r, i in enumerate(sorted(range(5), key=lambda i: -scores[i]), start=1)}

    print(f"{'#':<3}{'dự đoán':<9}{'thực tế':<9}{'score':<10}cặp câu")
    print("-" * 78)
    for i, (a, b) in enumerate(PAIRS):
        mark = "  <-- lệch" if PREDICTED_RANK[i] != actual_rank[i] else ""
        print(f"{i+1:<3}{PREDICTED_RANK[i]:<9}{actual_rank[i]:<9}{scores[i]:+.4f}   {a[:42]}...{mark}")
        print(f"{'':<21}{'':<10}   {b[:42]}...")

    hits = sum(1 for i in range(5) if PREDICTED_RANK[i] == actual_rank[i])
    print("-" * 78)
    print(f"Đoán đúng thứ hạng: {hits}/5")
    print(f"Cao nhất thực tế  : cặp {max(range(5), key=lambda i: scores[i]) + 1}  ({max(scores):+.4f})")
    print(f"Thấp nhất thực tế : cặp {min(range(5), key=lambda i: scores[i]) + 1}  ({min(scores):+.4f})")
    print("\nChép bảng trên vào REPORT_CANHAN mục 4, rồi tự viết phần")
    print("'điều gì khiến bạn ngạc nhiên nhất' — nhìn mấy dòng '<-- lệch' để có ý.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
