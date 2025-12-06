# [file name]: pdf_processor.py
import os
import re
from pathlib import Path
from typing import List, Dict, Any

from base_processor import BaseDocumentProcessor

# Импорты для PDF
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


class PDFProcessor(BaseDocumentProcessor):
    """Процессор для PDF файлов"""

    def can_process(self, file_path: str) -> bool:
        return file_path.lower().endswith('.pdf') and HAS_PDF and HAS_PDFPLUMBER

    def extract_text_with_tables_ordered(self, file_path: str) -> str:
        """Извлечение текста из PDF с таблицами"""
        try:
            full_content = []
            table_count = 0

            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_content = []

                    # Извлекаем таблицы
                    tables = page.find_tables()
                    table_bboxes = []

                    if tables:
                        for table in tables:
                            bbox = table.bbox
                            table_data = table.extract()

                            if table_data and any(any(cell for cell in row if cell) for row in table_data):
                                table_bboxes.append({
                                    'bbox': bbox,
                                    'data': table_data,
                                    'page_num': page_num
                                })

                    # Извлекаем текст
                    text = page.extract_text()
                    if text and text.strip():
                        # Базовая структуризация текста
                        lines = text.strip().split('\n')
                        for line in lines:
                            line = line.strip()
                            if line:
                                page_content.append(line)

                    # Добавляем таблицы
                    if table_bboxes:
                        # Сортируем таблицы по y-координате
                        table_bboxes.sort(key=lambda x: x['bbox'][1])

                        for table_info in table_bboxes:
                            table_content = self._format_table_universal(table_info['data'])
                            if table_content:
                                page_content.append(table_content)
                                table_count += 1

                    if page_content:
                        full_content.append(f"--- Страница {page_num} ---")
                        full_content.extend(page_content)
                        full_content.append("")  # Пустая строка между страницами

            result = '\n'.join(full_content)
            self.logger.info(f"PDF извлечен: {table_count} таблиц")
            return result

        except Exception as e:
            self.logger.warning(f"Ошибка PDFPlumber: {e}, используется резервный метод")
            return self._extract_text_fallback(file_path)

    def _format_table_universal(self, table_data: List[List[str]]) -> str:
        """Универсальное форматирование таблицы с шапкой 0-3 строк"""
        if not table_data:
            return ""

        formatted_lines = []
        formatted_lines.append("--- Таблица начало ---")
        
        # 1. Автоматическое определение количества строк шапки
        header_row_count = self._detect_header_rows(table_data)
        
        # 2. Разделение на шапку и данные
        header_rows = table_data[:header_row_count] if header_row_count > 0 else []
        data_rows = table_data[header_row_count:]
        
        # 3. Объединение шапки (если есть)
        if header_rows:
            merged_header = self._merge_header_columns(header_rows)
            if merged_header:
                formatted_lines.append(" | ".join(merged_header))
                # Добавляем разделитель
                separator = ['---'] * len(merged_header)
                formatted_lines.append(" | ".join(separator))
        
        # 4. Добавление данных
        for row in data_rows:
            if row and any(cell for cell in row if cell):
                cleaned_cells = [re.sub(r'\s+', ' ', str(cell).strip()) if cell else "" for cell in row]
                formatted_lines.append(" | ".join(cleaned_cells))
        
        formatted_lines.append("--- Таблица конец ---")
        formatted_lines.append("")
        return "\n".join(formatted_lines)

    def _detect_header_rows(self, table_data: List[List[str]]) -> int:
        """Автоматически определяет количество строк шапки (0-3)"""
        if not table_data:
            return 0
        
        max_header_rows = min(3, len(table_data))
        
        for i in range(max_header_rows):
            row = table_data[i]
            
            # Критерии для определения конца шапки:
            # 1. Следующая строка содержит числовые данные
            if i + 1 < len(table_data) and self._has_numeric_data(table_data[i + 1]):
                return i + 1
            
            # 2. Текущая строка выглядит как данные (длинный текст, числа)
            if self._looks_like_data_row(row):
                return i
            
            # 3. Текущая строка - явная шапка (короткий текст, заголовочные слова)
            if self._is_explicit_header_row(row):
                continue
                
            # 4. По умолчанию считаем первую строку шапкой
            if i == 0:
                continue
                
        return max_header_rows

    def _has_numeric_data(self, row: List[str]) -> bool:
        """Проверяет, содержит ли строка числовые данные"""
        for cell in row:
            if cell and re.search(r'\d+[,\.]\d+|\b\d+\b', str(cell)):
                return True
        return False

    def _looks_like_data_row(self, row: List[str]) -> bool:
        """Проверяет, выглядит ли строка как строка данных"""
        if not row:
            return False
        
        # Данные обычно содержат более длинный текст или числа
        total_chars = sum(len(str(cell)) for cell in row if cell)
        avg_chars_per_cell = total_chars / len(row)
        
        return avg_chars_per_cell > 25 or self._has_numeric_data(row)

    def _is_explicit_header_row(self, row: List[str]) -> bool:
        """Проверяет, является ли строка явной шапкой"""
        if not row:
            return False
        
        header_keywords = ['характеристика', 'показатель', 'параметр', 'наименование', 
                          'описание', 'тип', 'вид', 'категория', 'название']
        
        row_text = ' '.join(str(cell).lower() for cell in row if cell)
        has_header_keywords = any(keyword in row_text for keyword in header_keywords)
        
        # Шапка обычно короткая
        total_chars = sum(len(str(cell)) for cell in row if cell)
        avg_chars_per_cell = total_chars / len(row) if row else 0
        
        return has_header_keywords and avg_chars_per_cell < 30

    def _merge_header_columns(self, header_rows: List[List[str]]) -> List[str]:
        """Объединяет шапку по колонкам (вертикальное объединение)"""
        if not header_rows:
            return []
            
        if len(header_rows) == 1:
            return header_rows[0]
            
        # Определяем максимальное количество колонок
        max_cols = max(len(row) for row in header_rows)
        
        # Создаем объединенную шапку по колонкам
        merged_header = []
        
        for col_idx in range(max_cols):
            column_cells = []
            for row in header_rows:
                if col_idx < len(row) and row[col_idx]:
                    cell_text = str(row[col_idx]).strip()
                    if cell_text:
                        column_cells.append(cell_text)
            
            if column_cells:
                # Объединяем ячейки вертикально через пробел
                merged_cell = " ".join(column_cells)
                merged_cell = re.sub(r'\s+', ' ', merged_cell).strip()
                merged_header.append(merged_cell)
            else:
                merged_header.append("")
                
        return merged_header

    def _extract_text_fallback(self, file_path: str) -> str:
        """Резервный метод извлечения текста"""
        try:
            doc = fitz.open(file_path)
            full_content = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text", sort=True)

                if text.strip():
                    full_content.append(f"--- Страница {page_num + 1} ---")
                    lines = text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if line:
                            full_content.append(line)
                    full_content.append("")

            doc.close()
            return '\n'.join(full_content)

        except Exception as e:
            self.logger.error(f"Ошибка резервного метода извлечения текста: {e}")
            raise

    def convert_to_txt(self, file_path: str, output_dir: str) -> str:
        """Конвертация PDF в TXT"""
        try:
            self.logger.info(f"Конвертация PDF в TXT: {file_path}")

            text = self.extract_text_with_tables_ordered(file_path)

            output_path = os.path.join(output_dir, f"{Path(file_path).stem}.txt")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)

            self.logger.info(f"PDF конвертирован в: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Ошибка конвертации PDF {file_path}: {e}")
            raise