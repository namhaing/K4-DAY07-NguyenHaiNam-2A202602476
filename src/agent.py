from typing import Any, Callable

from .store import EmbeddingStore


class KnowledgeBaseAgent:
    """
    An agent that answers questions using a vector knowledge base.

    Retrieval-augmented generation (RAG) pattern:
        1. Retrieve top-k relevant chunks from the store.
        2. Build a prompt with the chunks as context.
        3. Call the LLM to generate an answer.
    """

    def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3, metadata_filter: dict[str, Any] | None = None) -> str:
        if self.store.get_collection_size() == 0:
            return "Không tìm thấy ngữ cảnh vì kho tri thức đang rỗng."

        results = self.store.search_with_filter(question, top_k=top_k, metadata_filter=metadata_filter)
        if not results:
            return "Không tìm thấy ngữ cảnh phù hợp để trả lời câu hỏi."

        context_blocks = []
        for index, result in enumerate(results, start=1):
            metadata = result.get("metadata", {})
            source = metadata.get("source") or metadata.get("title") or metadata.get("doc_id") or result.get("id", "unknown")
            context_blocks.append(f"[{index}] Source: {source}\n{result['content']}")

        prompt = (
            "Bạn là trợ lý trả lời câu hỏi dựa trên ngữ cảnh được cung cấp.\n"
            "Chỉ dùng thông tin trong ngữ cảnh; nếu không có thông tin, hãy nói rõ là không tìm thấy.\n"
            "Khi trả lời, hãy trích dẫn số nguồn như [1], [2] nếu dùng thông tin từ chunk đó.\n\n"
            f"Ngữ cảnh:\n{chr(10).join(context_blocks)}\n\n"
            f"Câu hỏi: {question}\n"
            "Câu trả lời:"
        )
        return self.llm_fn(prompt)
