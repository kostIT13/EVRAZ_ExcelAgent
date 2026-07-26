"""Excel Comment Extractor — извлекает комментарии из xl/comments*.xml.

openpyxl с data_only=True теряет комментарии.
Этот модуль читает их напрямую из ZIP-архива .xlsx файла.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from zipfile import ZipFile

from src.core.logging_settings import logger

# Пространства имён XML для комментариев Excel
NS = {
    'com': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'dc': 'http://purl.org/dc/elements/1.1/',
}


@dataclass
class ParsedComment:
    """Один Excel-комментарий."""
    cell_ref: str
    author: Optional[str]
    text: str
    row_num: int
    col_index: int
    sheet_name: str = ""


def _cell_ref_to_rc(cell_ref: str) -> tuple[int, int]:
    """Преобразует 'A1' → (1, 1), 'C12' → (12, 3)."""
    import re
    match = re.match(r'([A-Z]+)(\d+)', cell_ref.upper())
    if not match:
        return (0, 0)
    col_str, row_str = match.group(1), match.group(2)
    col = 0
    for c in col_str:
        col = col * 26 + (ord(c) - ord('A') + 1)
    return (int(row_str), col)


def _get_sheet_name_from_comment_file(comment_filename: str) -> str:
    """Извлекает имя листа из имени файла комментария.

    Примеры:
        xl/comments1.xml → Лист1
        xl/worksheets/_rels/sheet2.xml.comments → sheet2
    """
    import re
    # Пробуем найти номер листа
    match = re.search(r'comments(\d+)', comment_filename)
    if match:
        sheet_num = int(match.group(1))
        return f"Лист{sheet_num}"
    return ""


def extract_comments(file_path: Path) -> List[ParsedComment]:
    """Извлекает все комментарии из .xlsx файла.

    Args:
        file_path: Путь к .xlsx файлу.

    Returns:
        Список ParsedComment.
    """
    comments: List[ParsedComment] = []

    if not file_path.exists():
        logger.warning("File not found: {}", file_path)
        return comments

    try:
        with ZipFile(file_path, 'r') as z:
            # Ищем все файлы комментариев
            comment_files = [f for f in z.namelist() if 'comments' in f and f.endswith('.xml')]

            if not comment_files:
                logger.debug("No comment files found in {}", file_path.name)
                return comments

            for comment_file in comment_files:
                try:
                    content = z.read(comment_file)
                    sheet_name = _get_sheet_name_from_comment_file(comment_file)
                    parsed = _parse_comment_xml(content, sheet_name)
                    comments.extend(parsed)
                except Exception as exc:
                    logger.warning("Failed to parse {}: {}", comment_file, exc)

        logger.info("Extracted {} comments from {}", len(comments), file_path.name)
    except Exception as exc:
        logger.error("Failed to open {}: {}", file_path, exc)

    return comments


def _parse_comment_xml(xml_content: bytes, sheet_name: str = "") -> List[ParsedComment]:
    """Парсит XML комментариев Excel."""
    comments: List[ParsedComment] = []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.warning("Failed to parse comment XML: {}", exc)
        return comments

    # Ищем все <comment> элементы
    for comment_elem in root.iter():
        tag = comment_elem.tag
        if tag.endswith('comment') or tag.endswith('Comment'):
            cell_ref = comment_elem.get('ref', '')

            # Извлекаем автора
            author = None
            author_elem = comment_elem.find('.//dc:creator', NS)
            if author_elem is not None and author_elem.text:
                author = author_elem.text.strip()

            # Извлекаем текст
            text_parts = []
            for t_elem in comment_elem.iter():
                t_tag = t_elem.tag
                if (t_tag.endswith('t') or t_tag.endswith('Text')) and t_elem.text:
                    text_parts.append(t_elem.text)

            text = ' '.join(text_parts).strip()
            if not text:
                continue

            row_num, col_index = _cell_ref_to_rc(cell_ref)

            comments.append(ParsedComment(
                cell_ref=cell_ref,
                author=author,
                text=text,
                row_num=row_num,
                col_index=col_index,
                sheet_name=sheet_name,
            ))

    return comments