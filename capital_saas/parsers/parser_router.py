from pathlib import Path

from parsers.docx_parser import DocxParser
from parsers.excel_parser import ExcelParser
from parsers.image_parser import ImageParser
from parsers.pdf_parser import PDFParser


PARSERS = {
    ".xls": ExcelParser, ".xlsx": ExcelParser,
    ".doc": DocxParser, ".docx": DocxParser,
    ".pdf": PDFParser,
    ".png": ImageParser, ".jpg": ImageParser, ".jpeg": ImageParser,
}


def parser_for(file_path: Path):
    parser_class = PARSERS.get(file_path.suffix.lower())
    if not parser_class:
        raise ValueError(f"没有可用解析器：{file_path.suffix}")
    return parser_class()


def parse_document(file_path: Path) -> dict:
    parser = parser_for(file_path)
    return parser.parse(file_path)
