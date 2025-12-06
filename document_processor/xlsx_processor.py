# [file name]: xlsx_processor.py
import os
import re
from pathlib import Path
from typing import List, Dict, Any

from base_processor import BaseDocumentProcessor

# Импорты для XLSX
try:
    import pandas as pd
    import openpyxl
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False


class XLSXProcessor(BaseDocumentProcessor):
    """Процессор для XLSX файлов"""

    def can_process(self, file_path: str) -> bool:
        return file_path.lower().endswith('.xlsx') and HAS_XLSX

    def extract_sheets_content(self, file_path: str) -> str:
        """Извлечение содержимого всех листов XLSX"""
        try:
            content_lines = []
            
            # Открываем файл для получения информации о листах
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheet_names = workbook.sheetnames
            
            for sheet_name in sheet_names:
                sheet_content = self._extract_sheet_content(file_path, sheet_name)
                if sheet_content:
                    content_lines.append(f"--- Лист: {sheet_name} ---")
                    content_lines.append(sheet_content)
                    content_lines.append("")  # Пустая строка между листами
            
            workbook.close()
            return '\n'.join(content_lines)
            
        except Exception as e:
            self.logger.error(f"Ошибка извлечения содержимого XLSX {file_path}: {e}")
            raise

    def _extract_sheet_content(self, file_path: str, sheet_name: str) -> str:
        """Извлечение содержимого конкретного листа"""
        try:
            # Используем pandas для чтения данных
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, dtype=str)
            
            if df.empty:
                return ""
            
            content_lines = []
            table_data = []
            
            # Преобразуем DataFrame в список списков
            for _, row in df.iterrows():
                row_data = [str(cell) if pd.notna(cell) else "" for cell in row]
                table_data.append(row_data)
            
            if not table_data:
                return ""
            
            # Форматируем как таблицу
            formatted_table = self._format_table_universal(table_data)
            if formatted_table:
                content_lines.append(formatted_table)
            
            return '\n'.join(content_lines)
            
        except Exception as e:
            self.logger.warning(f"Ошибка извлечения листа {sheet_name}: {e}")
            return ""

    def _format_table_universal(self, table_data: List[List[str]]) -> str:
        """Универсальное форматирование таблицы с шапкой 0-3 строк"""
        if not table_data:
            return ""

        table_lines = []
        table_lines.append("--- Таблица начало ---")
        
        # 1. Автоматическое определение количества строк шапки
        header_row_count = self._detect_header_rows(table_data)
        
        # 2. Разделение на шапку и данные
        header_rows = table_data[:header_row_count] if header_row_count > 0 else []
        data_rows = table_data[header_row_count:]
        
        # 3. Объединение шапки (если есть)
        if header_rows:
            merged_header = self._merge_header_columns(header_rows)
            if merged_header:
                table_lines.append(" | ".join(merged_header))
                # Добавляем разделитель
                separator = ['---'] * len(merged_header)
                table_lines.append(" | ".join(separator))
        
        # 4. Добавление данных
        for row in data_rows:
            if row and any(cell for cell in row if cell):
                cleaned_cells = [re.sub(r'\s+', ' ', str(cell).strip()) if cell else "" for cell in row]
                table_lines.append(" | ".join(cleaned_cells))
        
        table_lines.append("--- Таблица конец ---")
        table_lines.append("")
        return "\n".join(table_lines)

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

    def convert_to_txt(self, file_path: str, output_dir: str) -> str:
        """Конвертация XLSX в TXT"""
        try:
            self.logger.info(f"Конвертация XLSX в TXT: {file_path}")

            text = self.extract_sheets_content(file_path)

            output_path = os.path.join(output_dir, f"{Path(file_path).stem}.txt")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)

            self.logger.info(f"XLSX конвертирован в: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Ошибка конвертации XLSX {file_path}: {e}")
            raise