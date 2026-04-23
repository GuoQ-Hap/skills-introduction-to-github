from pathlib import Path
from typing import Optional

from Base.RicUtils.pdfUtils import extract_pdf_text
from LMA.constants import CHUNK_OVERLAP, CHUNK_SIZE
from LMA.service.base import service_logger
from LMA.ai.embedding.leangState import ChunkStrategy, SourceKind

logger = service_logger

# 智能切分：优先大段落 → 换行 → 中英文句末 → 标点 → 空格 → 字符
_SMART_SEPARATORS = [
    "\n\n",
    "\r\n\r\n",
    "\n",
    "。\n",
    "。", "！", "？",
    ". ", "! ", "? ",
    "；", "; ",
    "，", ", ",
    " ",
    "",
]


class TextService:
    def load_text(self, path: str, kind: SourceKind) -> Optional[str]:
        file_path = Path(path)
        if not file_path.exists():
            logger.error("文件不存在: %s", path)
            return None
        suffix = file_path.suffix.lower()
        if kind == SourceKind.PDF_FORMATTED:
            if suffix != ".pdf":
                logger.error("pdf_formatted 仅支持 PDF 文件")
                return None
            return extract_pdf_text(path)

        if suffix == ".pdf":
            return self._pdf_plain_text(path)
        return self._plain_text(path)

    def split_text(
        self,
        text: str,
        strategy: ChunkStrategy,
        chunk_size: int = CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
    ) -> list[str]:
        if not text or not text.strip():
            return []
        if strategy == ChunkStrategy.SMART:
            return self._chunk_smart(text, chunk_size, overlap)
        return self._chunk_fixed_window(text, chunk_size, overlap)

    def chunk_text(self, text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
        """兼容旧调用：等价于固定滑窗。"""
        return self._chunk_fixed_window(text, chunk_size, overlap)

    def _chunk_fixed_window(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        if overlap >= chunk_size:
            overlap = max(0, chunk_size // 8)
        chunks: list[str] = []
        start = 0
        n = len(text.strip())
        source = text.strip()
        while start < n:
            end = min(start + chunk_size, n)
            part = source[start:end].strip()
            if part:
                chunks.append(part)
            if end >= n:
                break
            start = end - overlap
        return chunks

    def _chunk_smart(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        if overlap >= chunk_size:
            overlap = max(0, chunk_size // 8)
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            logger.warning("langchain_text_splitters 不可用，回退为 fixed 切分")
            return self._chunk_fixed_window(text, chunk_size, overlap)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=_SMART_SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )
        raw = splitter.split_text(text.strip())
        return [c.strip() for c in raw if c and c.strip()]

    def _pdf_plain_text(self, pdf_path: str) -> Optional[str]:
        try:
            import PyPDF2
        except ImportError:
            logger.error("读取 PDF 需要 PyPDF2")
            return None
        parts: list[str] = []
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text and text.strip():
                        parts.append(text.strip())
        except Exception as e:
            logger.error("提取 PDF 文本失败: %s", e)
            return None
        return "\n".join(parts) if parts else None

    def _plain_text(self, path: str) -> Optional[str]:
        try:
            return Path(path).read_bytes().decode("utf-8", errors="replace")
        except Exception as e:
            logger.error("读取文件失败: %s", e)
            return None


text_service = TextService()
