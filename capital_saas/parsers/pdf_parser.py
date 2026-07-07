from pathlib import Path

from pypdf import PdfReader

from parsers.base_parser import BaseParser


class PDFParser(BaseParser):
    parser_type = "pdf"

    def parse(self, file_path: Path) -> dict:
        reader = PdfReader(str(file_path))
        pages = []
        for page in reader.pages[:50]:
            pages.append((page.extract_text() or "").strip())
        text = "\n".join(value for value in pages if value)
        return {
            "parser_type": self.parser_type,
            "status": "success" if text else "needs_ocr",
            "page_count": len(reader.pages),
            "text_summary": text[:10000],
            "needs_ocr": not bool(text),
            "message": "PDF未提取到可复制文本，建议进入OCR流程" if not text else "PDF文本提取成功",
        }
