from pathlib import Path

from parsers.base_parser import BaseParser


class ImageParser(BaseParser):
    parser_type = "image"

    def parse(self, file_path: Path) -> dict:
        return {
            "parser_type": self.parser_type,
            "status": "pending_ocr",
            "ocr_status": "pending_ocr",
            "message": "图片已保存，本阶段未启用OCR；后续可接入OCR服务。",
            "file_name": file_path.name,
        }
