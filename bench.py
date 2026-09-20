"""Công cụ đo benchmark retrieval — Lab 07 Data Foundations (Nam, nhóm G).

Chạy 5 benchmark query của nhóm trên corpus đã crawl, in top-3 và chấm 2 mức.

    python bench.py                  # chạy đủ 5 câu + A/B filter
    python bench.py --top-k 5        # đổi top-k
    python bench.py --corpus data/x  # đổi thư mục corpus
    python bench.py --strategy heading
    python bench.py --all-strategies # chạy Fixed/Recursive/Heading/Clause để so sánh nhóm
    python bench.py --all-strategies --output ket_qua_benchmark.txt

Cần `src/` đã hoàn thiện (pytest tests/ -v = 42 passed).
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

# Console Windows mặc định là cp1252, không in được tiếng Việt.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs) -> bool:
        return False

from src import (
    EMBEDDING_PROVIDER_ENV,
    GEMINI_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_MODEL,
    OPENAI_EMBEDDING_MODEL,
    Document,
    EmbeddingStore,
    FixedSizeChunker,
    GeminiEmbedder,
    LocalEmbedder,
    OpenAIEmbedder,
    RecursiveChunker,
    SentenceChunker,
    _mock_embed,
)


class TeeWriter:
    """Ghi đồng thời ra console và file UTF-8, tránh PowerShell Tee-Object làm hỏng tiếng Việt."""

    def __init__(self, *streams) -> None:
        self.streams = streams
        self.encoding = getattr(streams[0], "encoding", "utf-8") if streams else "utf-8"

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


class HeadingChunker:
    """Chunk theo heading; section dài thì hạ xuống RecursiveChunker và gắn lại heading."""

    def __init__(self, max_chars: int = 800, heading_pattern: str = r"^#{1,6}\s+") -> None:
        self.max_chars = max(1, max_chars)
        self.heading_pattern = heading_pattern

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        sections: list[list[str]] = []
        current: list[str] = []
        for line in text.splitlines():
            if re.match(self.heading_pattern, line) and current:
                sections.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append(current)

        chunks: list[str] = []
        for section_lines in sections:
            section = "\n".join(section_lines).strip()
            if not section:
                continue
            if len(section) <= self.max_chars:
                chunks.append(section)
                continue

            heading = section_lines[0].strip() if re.match(self.heading_pattern, section_lines[0]) else ""
            body = "\n".join(section_lines[1:] if heading else section_lines).strip()
            child_size = max(1, self.max_chars - len(heading) - 1) if heading else self.max_chars
            fallback = RecursiveChunker(chunk_size=child_size)
            for piece in fallback.chunk(body):
                chunks.append(f"{heading}\n{piece}".strip())
        return chunks


class ClauseChunker:
    """Chunk theo điều/khoản/điểm trong văn bản chính sách Shopee."""

    def __init__(
        self,
        max_chars: int = 400,
        min_chars: int = 80,
        clause_pattern: str = r"^(?:\d+(?:\.\d+)*\.|[ivxlcdm]{2,}\.|[a-z]\.)\s+",
    ) -> None:
        self.max_chars = max(1, max_chars)
        self.min_chars = max(1, min_chars)
        self.clause_pattern = clause_pattern
        self.heading_pattern = r"^#{1,6}\s+"

    def chunk(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        heading = ""
        clauses: list[str] = []
        current: list[str] = []

        def flush_current() -> None:
            if current:
                clause = "\n".join(current).strip()
                if clause:
                    clauses.append(f"{heading}\n{clause}".strip() if heading else clause)
                current.clear()

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current:
                    current.append("")
                continue
            if re.match(self.heading_pattern, stripped):
                flush_current()
                heading = stripped
                continue
            if re.match(self.clause_pattern, stripped):
                flush_current()
                current.append(stripped)
            else:
                current.append(stripped)
        flush_current()

        merged = self._merge_short_clauses(clauses)
        return self._split_long_clauses(merged)

    def _merge_short_clauses(self, clauses: list[str]) -> list[str]:
        merged: list[str] = []
        for clause in clauses:
            if merged and len(merged[-1]) < self.min_chars and len(merged[-1]) + 1 + len(clause) <= self.max_chars:
                merged[-1] = f"{merged[-1]}\n{clause}".strip()
            else:
                merged.append(clause)
        return merged

    def _split_long_clauses(self, clauses: list[str]) -> list[str]:
        chunks: list[str] = []
        for clause in clauses:
            if len(clause) <= self.max_chars:
                chunks.append(clause)
                continue

            lines = clause.splitlines()
            prefix = lines[0].strip() if lines and re.match(self.heading_pattern, lines[0].strip()) else ""
            body = "\n".join(lines[1:] if prefix else lines).strip()
            child_size = max(1, self.max_chars - len(prefix) - 1) if prefix else self.max_chars
            fallback = RecursiveChunker(chunk_size=child_size)
            for piece in fallback.chunk(body):
                chunks.append(f"{prefix}\n{piece}".strip())
        return chunks


class CachedEmbedder:
    """File cache đơn giản để chạy lại embedder trả phí mà không tốn thêm lượt."""

    FLUSH_EVERY = 25
    BATCH_SIZE = 50

    def __init__(self, embedder, cache_path: Path = Path(".embedding_cache.json")) -> None:
        self.embedder = embedder
        self.cache_path = cache_path
        self.model_tag = getattr(embedder, "_backend_name", embedder.__class__.__name__)
        self._backend_name = f"{self.model_tag} + file cache"
        self.hits = self.misses = 0
        self._unsaved = 0
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            self.cache = {}
        atexit.register(self.save)

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_tag}|{text}".encode("utf-8")).hexdigest()

    def __call__(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def _retry_delay_seconds(self, error: Exception) -> float | None:
        message = str(error)
        if "RESOURCE_EXHAUSTED" not in message and "429" not in message:
            return None

        patterns = [
            r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s",
            r"retry in (\d+(?:\.\d+)?)s",
            r"retry in (\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.I)
            if match:
                return float(match.group(1)) + 2.0
        return 65.0

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str, str]] = []
        for index, text in enumerate(texts):
            key = self._key(text)
            if key in self.cache:
                self.hits += 1
                results[index] = [float(value) for value in self.cache[key]]
            else:
                missing.append((index, text, key))

        embed_many = getattr(self.embedder, "embed_many", None)
        for start in range(0, len(missing), self.BATCH_SIZE):
            batch = missing[start : start + self.BATCH_SIZE]
            batch_texts = [item[1] for item in batch]
            for attempt in range(3):
                try:
                    if callable(embed_many):
                        vectors = embed_many(batch_texts)
                    else:
                        vectors = [self.embedder(text) for text in batch_texts]
                    break
                except Exception as error:  # noqa: BLE001 - external embedding backends raise SDK-specific errors
                    delay = self._retry_delay_seconds(error)
                    if delay is None or attempt == 2:
                        raise
                    print(f"  ! Backend hết quota tạm thời; chờ {delay:.0f}s rồi thử lại batch embedding...")
                    time.sleep(delay)

            for (index, _text, key), vector in zip(batch, vectors):
                clean_vector = [float(value) for value in vector]
                self.cache[key] = clean_vector
                results[index] = clean_vector
                self.misses += 1
                self._unsaved += 1
            if self._unsaved >= self.FLUSH_EVERY:
                self.save()

        self.save()
        return [vector or [] for vector in results]

    def save(self) -> None:
        if not self._unsaved:
            return
        self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")
        self._unsaved = 0


# ---------------------------------------------------------------------------
# ĐÂY LÀ DÒNG DUY NHẤT MỖI NGƯỜI ĐỔI — chiến lược chunking của riêng mình.
#   Duy  : FixedSizeChunker(chunk_size=500, overlap=50)
#   Tâm  : RecursiveChunker(chunk_size=400)
#   Hiền : HeadingChunker(max_chars=800)        <- tự viết
#   Nam  : ClauseChunker(max_chars=400)         <- tự viết, xem CHECKLIST_NAM.md muc E1
# Mọi thứ khác giữ nguyên để so sánh giữa 4 người mới công bằng.
# ---------------------------------------------------------------------------
CHUNKER = ClauseChunker(max_chars=400)

CORPUS_DIR = Path("data/Bao_hanh")


def build_strategies() -> dict[str, object]:
    return {
        "fixed": FixedSizeChunker(chunk_size=500, overlap=50),
        "recursive": RecursiveChunker(chunk_size=400),
        "heading": HeadingChunker(max_chars=800),
        "clause": ClauseChunker(max_chars=400),
    }

# ---------------------------------------------------------------------------
# 5 benchmark query của nhóm (REPORT_NHOM mục 3).
#   expect_docs   : doc_id được coi là tài liệu gold  -> chấm MỨC 1
#   expect_any    : chuỗi đặc trưng phải xuất hiện trong ngữ cảnh truy xuất được
#                   -> chấm MỨC 2 (cách chấm thật theo docs/SCORING.md)
#   filter        : metadata_filter, None nếu câu không cần lọc
# ---------------------------------------------------------------------------
QUERIES = [
    {
        "id": 1,
        "question": "Bảo hành sản phẩm thông qua Shopee mất bao lâu?",
        "expect_docs": ["shopee-chinh-sach-bao-hanh-san-pham"],
        "expect_any": ["20 ngày đến 45 ngày"],
        "filter": None,
    },
    {
        "id": 2,
        "question": "Sản phẩm cần thỏa những điều kiện gì để được bảo hành miễn phí?",
        "expect_docs": ["shopee-chinh-sach-bao-hanh-san-pham"],
        "expect_any": ["lỗi kỹ thuật do nhà sản xuất"],
        "filter": None,
    },
    {
        "id": 3,
        "question": "Thời hạn gửi yêu cầu Trả hàng/Hoàn tiền với từng loại đơn hàng là bao lâu?",
        "expect_docs": ["shopee-quy-dinh-chung-tra-hang-hoan-tien"],
        "expect_any": ["15 ngày", "24 giờ"],
        "filter": None,
    },
    {
        "id": 4,
        "question": "Người bán được đăng bán hàng hóa còn bao nhiêu hạn sử dụng?",
        "expect_docs": ["shopee-quy-dinh-dang-ban-san-pham"],
        "expect_any": ["30% thời hạn sử dụng"],
        "filter": None,
    },
    {
        # Câu cần metadata_filter. Chỉ hoạt động SAU KHI tách
        # shopee-chinh-sach-tra-hang-hoan-tien.md thành 2 file buyer/seller.
        "id": 5,
        "question": "Bên liên quan có bao nhiêu ngày để xử lý yêu cầu trả hàng/hoàn tiền?",
        "expect_docs": ["shopee-chinh-sach-tra-hang-hoan-tien-nguoi-mua"],
        "expect_any": ["15 (mười lăm) ngày"],
        "filter": {"audience": "buyer"},
        "ab_filters": [
            {"label": "buyer", "filter": {"audience": "buyer"}, "expect_any": ["15 (mười lăm) ngày"]},
            {"label": "seller", "filter": {"audience": "seller"}, "expect_any": ["02 ngày lịch"]},
        ],
    },
]


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Tách YAML front matter thành metadata, phần còn lại là content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not match:
        return {}, raw
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        pair = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line.strip())
        if pair:
            metadata[pair.group(1)] = pair.group(2).strip().strip('"').strip("'")
    return metadata, match.group(2)


def load_chunks(corpus_dir: Path, chunker=CHUNKER) -> list[Document]:
    """Đọc từng .md, chunk phần thân NGOÀI store, trải frontmatter vào mọi chunk."""
    documents: list[Document] = []
    for path in sorted(corpus_dir.glob("*.md")):
        metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        for index, chunk in enumerate(chunker.chunk(body)):
            if not chunk.strip():
                continue
            documents.append(
                Document(
                    id=f"{path.stem}#{index}",
                    content=chunk,
                    metadata={**metadata, "doc_id": path.stem},
                )
            )
    return documents


def pick_embedder():
    """Chọn embedding backend theo .env, rơi về mock nếu thiếu cấu hình."""
    load_dotenv(override=False)
    provider = os.getenv(EMBEDDING_PROVIDER_ENV, "mock").strip().lower()
    try:
        if provider == "local":
            return LocalEmbedder(model_name=os.getenv("LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL))
        if provider == "openai":
            return CachedEmbedder(OpenAIEmbedder(model_name=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL)))
        if provider == "gemini":
            return CachedEmbedder(GeminiEmbedder(model_name=os.getenv("GEMINI_EMBEDDING_MODEL", GEMINI_EMBEDDING_MODEL)))
    except Exception as error:  # noqa: BLE001 - backend tùy chọn, hỏng thì dùng mock
        print(f"  ! Không dùng được backend '{provider}' ({error}); rơi về mock.")
    return _mock_embed


def score_query(spec: dict, results: list[dict]) -> tuple[int, int, str]:
    """Chấm 2 mức. Trả (điểm_mức_1, điểm_mức_2, ghi chú).

    Mức 1 — chấm theo doc_id (cách ngây thơ, THỔI PHỒNG kết quả).
    Mức 2 — chấm theo nội dung: ngữ cảnh truy xuất được có chứa chuỗi đặc trưng không.
    Thang: 2đ gold ở top-1, 1đ gold ở top-2/3, 0đ vắng.
    """
    ranks = [i for i, r in enumerate(results, start=1) if r["metadata"].get("doc_id") in spec["expect_docs"]]
    level1 = 2 if ranks and ranks[0] == 1 else (1 if ranks else 0)

    context = "\n".join(r["content"] for r in results).lower()
    found = [s for s in spec["expect_any"] if s.lower() in context]
    missing = [s for s in spec["expect_any"] if s.lower() not in context]
    if missing:
        return level1, 0, f"ngữ cảnh thiếu: {', '.join(missing)}"

    content_ranks = [
        rank
        for rank, result in enumerate(results, start=1)
        if any(signature.lower() in result["content"].lower() for signature in spec["expect_any"])
    ]
    level2 = 2 if content_ranks and content_ranks[0] == 1 else (1 if content_ranks else 0)
    return level1, level2, f"tìm thấy: {', '.join(found)}"


def show(results: list[dict], indent: str = "    ") -> None:
    for rank, item in enumerate(results, start=1):
        preview = " ".join(item["content"].split())[:90]
        audience = item["metadata"].get("audience", "?")
        print(f"{indent}{rank}. score={item['score']:+.4f}  {item['metadata'].get('doc_id')}  audience={audience}")
        print(f"{indent}   {preview}...")


def run_strategy(name: str, chunker, corpus_dir: Path, top_k: int, embedder) -> dict:
    print("=" * 78)
    print(f"CHIẾN LƯỢC : {name} / {chunker.__class__.__name__}  {vars(chunker)}")
    print(f"CORPUS     : {corpus_dir}")

    documents = load_chunks(corpus_dir, chunker)
    store = EmbeddingStore(collection_name=f"bench_{name}", embedding_fn=embedder)
    store.add_documents(documents)
    lengths = [len(d.content) for d in documents]
    doc_count = len({d.metadata["doc_id"] for d in documents})
    print(f"ĐÃ NẠP     : {store.get_collection_size()} chunk từ {doc_count} tài liệu")
    print(
        f"ĐỘ DÀI CHUNK: trung bình {sum(lengths) // max(1, len(lengths))} ký tự, "
        f"min {min(lengths, default=0)}, max {max(lengths, default=0)}"
    )
    print("=" * 78)

    total_doc_id = total_content = 0
    per_query: list[dict] = []
    for spec in QUERIES:
        print(f"\n[{spec['id']}] {spec['question']}")
        if spec["filter"]:
            print(f"    filter = {spec['filter']}")
        results = store.search_with_filter(spec["question"], top_k=top_k, metadata_filter=spec["filter"])
        if not results:
            print("    (không có kết quả — kiểm tra lại metadata_filter)")
            per_query.append({"id": spec["id"], "doc_id_score": 0, "content_score": 0, "results": []})
            continue
        show(results)
        doc_id_score, content_score, note = score_query(spec, results)
        total_doc_id += doc_id_score
        total_content += content_score
        per_query.append(
            {
                "id": spec["id"],
                "question": spec["question"],
                "doc_id_score": doc_id_score,
                "content_score": content_score,
                "note": note,
                "results": results,
            }
        )
        flag = "" if doc_id_score == content_score else "   <-- CHÊNH LỆCH, đây là phát hiện đáng viết vào báo cáo"
        print(f"    chấm theo doc_id : {doc_id_score}/2")
        print(f"    chấm theo nội dung: {content_score}/2  ({note}){flag}")

    print("\n" + "=" * 78)
    print(f"TỔNG chấm theo doc_id  : {total_doc_id}/10   <- cách ngây thơ, thổi phồng")
    print(f"TỔNG chấm theo nội dung: {total_content}/10   <- cách đúng theo docs/SCORING.md")
    print("=" * 78)

    spec = next(q for q in QUERIES if q["filter"])
    print(f"\n### A/B FILTER — {name} — câu {spec['id']}: {spec['question']}")
    unfiltered = store.search_with_filter(spec["question"], top_k=top_k, metadata_filter=None)
    print(f"\n  [A] KHÔNG filter")
    show(unfiltered, indent="      ")

    ab_filter_runs = []
    filters_to_compare = spec.get("ab_filters", [{"label": "target", "filter": spec["filter"]}])
    for offset, filter_spec in enumerate(filters_to_compare):
        letter = chr(ord("B") + offset)
        filtered = store.search_with_filter(spec["question"], top_k=top_k, metadata_filter=filter_spec["filter"])
        print(f"\n  [{letter}] CÓ filter {filter_spec['filter']} ({filter_spec.get('label', 'target')})")
        show(filtered, indent="      ")
        expected_strings = filter_spec.get("expect_any", [])
        if expected_strings:
            context = "\n".join(item["content"] for item in filtered).lower()
            found = [text for text in expected_strings if text.lower() in context]
            missing = [text for text in expected_strings if text.lower() not in context]
            if found:
                print(f"      chuỗi đáp án thấy được: {', '.join(found)}")
            if missing:
                print(f"      chuỗi đáp án còn thiếu: {', '.join(missing)}")
        ab_filter_runs.append(
            {
                "label": filter_spec.get("label", "target"),
                "filter": filter_spec["filter"],
                "results": filtered,
                "doc_ids": [item["metadata"].get("doc_id") for item in filtered],
                "audiences": [item["metadata"].get("audience") for item in filtered],
            }
        )

    unfiltered_doc_ids = [item["metadata"].get("doc_id") for item in unfiltered]
    filtered_doc_ids = ab_filter_runs[0]["doc_ids"] if ab_filter_runs else []
    filter_changed = any(unfiltered_doc_ids != run["doc_ids"] for run in ab_filter_runs)
    if filter_changed:
        print("\n  Nhận xét: filter đổi tập top-k, dùng được làm ví dụ metadata_filter.")
    else:
        print("\n  Nhận xét: hai lần giống nhau, câu hỏi hoặc corpus chưa chứng minh rõ lợi ích filter.")

    return {
        "name": name,
        "chunk_count": len(documents),
        "avg_length": sum(lengths) / max(1, len(lengths)),
        "doc_id_score": total_doc_id,
        "content_score": total_content,
        "filter_changed": filter_changed,
        "ab_unfiltered": unfiltered_doc_ids,
        "ab_filtered": filtered_doc_ids,
        "ab_filter_runs": ab_filter_runs,
        "per_query": per_query,
    }


def main() -> int:
    strategies = build_strategies()
    parser = argparse.ArgumentParser(description="Chạy benchmark retrieval cho Lab 07.")
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--strategy", choices=sorted(strategies), default="clause")
    parser.add_argument("--all-strategies", action="store_true")
    parser.add_argument("--output", type=Path, help="Ghi bản sao output ra file UTF-8, ví dụ ket_qua_benchmark.txt")
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"Không thấy thư mục corpus: {args.corpus}")
        return 2

    original_stdout = sys.stdout
    output_handle = None
    if args.output:
        output_handle = args.output.open("w", encoding="utf-8", newline="")
        sys.stdout = TeeWriter(original_stdout, output_handle)

    try:
        embedder = pick_embedder()
        backend = getattr(embedder, "_backend_name", embedder.__class__.__name__)
        print(f"EMBEDDER   : {backend}")
        if embedder is _mock_embed:
            print("  ! MockEmbedder băm MD5, KHÔNG mã hoá ngữ nghĩa — số liệu dưới đây là nhiễu.")
            print("  ! Phải ghi rõ điều này trong báo cáo nếu dùng để phân tích.")

        selected = strategies.items() if args.all_strategies else [(args.strategy, strategies[args.strategy])]
        summaries = [run_strategy(name, chunker, args.corpus, args.top_k, embedder) for name, chunker in selected]

        if len(summaries) > 1:
            print("\n" + "=" * 78)
            print("BẢNG SO SÁNH CHIẾN LƯỢC")
            print("| Chiến lược | Số chunk | Avg length | Doc-id score | Content score | A/B filter đổi top-k? |")
            print("|---|---:|---:|---:|---:|---|")
            for summary in summaries:
                changed = "có" if summary["filter_changed"] else "không"
                print(
                    f"| {summary['name']} | {summary['chunk_count']} | {summary['avg_length']:.1f} | "
                    f"{summary['doc_id_score']}/10 | {summary['content_score']}/10 | {changed} |"
                )
            print("=" * 78)
    finally:
        if output_handle:
            sys.stdout.flush()
            sys.stdout = original_stdout
            output_handle.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
