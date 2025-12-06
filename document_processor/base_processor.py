# [file name]: base_processor.py
import json
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from abc import ABC, abstractmethod


class BaseDocumentProcessor(ABC):
    """Базовый класс для обработки документов"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def can_process(self, file_path: str) -> bool:
        """Может ли процессор обработать данный файл"""
        pass
    
    @abstractmethod
    def convert_to_txt(self, file_path: str, output_dir: str) -> str:
        """Конвертация файла в TXT"""
        pass


class DocumentPostProcessor:
    """Класс для пост-обработки и улучшения структуры документов"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def extract_metadata_and_title(self, content: str, file_path: str) -> Tuple[str, Dict[str, str]]:
        """Извлекает заголовок и метаданные документа"""
        lines = content.split('\n')
        metadata = {}
        
        # Поиск метаданных в первых 20 строках
        for line in lines[:20]:
            self._extract_metadata_from_line(line.strip(), metadata)
        
        # Формируем заголовок из метаданных
        title = self._create_title_from_metadata(metadata, file_path)
        
        return title, metadata
    
    def _extract_metadata_from_line(self, line: str, metadata: Dict[str, str]):
        """Извлекает метаданные из строки"""
        # Код документа (СП, ГОСТ и т.д.)
        code_match = re.search(r'(СП|ГОСТ|СНиП|ТР)\s+[\d\.\-]+', line)
        if code_match and 'code' not in metadata:
            metadata['code'] = code_match.group(0)
        
        # ОКС
        oks_match = re.search(r'ОКС\s+[\d\.]+', line)
        if oks_match and 'oks' not in metadata:
            metadata['oks'] = oks_match.group(0).replace('ОКС ', '')
        
        # ОКВЭД
        okved_match = re.search(r'ОК\s*ВЭД\s+[A-Z]\s+\d+', line)
        if okved_match and 'okved' not in metadata:
            metadata['okved'] = okved_match.group(0)
        
        # Дата введения
        date_match = re.search(r'Дата введения\s+[\d\-\.]+', line)
        if date_match and 'date_intro' not in metadata:
            metadata['date_intro'] = date_match.group(0).replace('Дата введения ', '')
        
        # Название документа (ищем многострочное название)
        if 'code' in metadata and 'title' not in metadata:
            # Ищем текст после кода документа
            code_pos = line.find(metadata['code'])
            if code_pos != -1:
                remaining_text = line[code_pos + len(metadata['code']):].strip()
                if remaining_text and len(remaining_text) > 5:
                    metadata['title'] = remaining_text
    
    def _create_title_from_metadata(self, metadata: Dict[str, str], file_path: str) -> str:
        """Создает заголовок документа из метаданных"""
        title_parts = []
        
        if 'code' in metadata:
            title_parts.append(metadata['code'])
        
        if 'title' in metadata:
            title_parts.append(metadata['title'])
        
        if title_parts:
            return ' '.join(title_parts)
        else:
            # Если метаданных нет, используем имя файла
            return Path(file_path).stem

    def process_title_section(self, content: str) -> str:
        """Обрабатывает титульную часть документа до предисловия"""
        lines = content.split('\n')
        processed_lines = []
        in_title_section = True

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Конец титульной части - начало предисловия (любого уровня)
            if ('Предисловие' in line_stripped and
                    (line_stripped.startswith('#') or
                     any(word in line_stripped for word in ['Предисловие', 'ПРЕДИСЛОВИЕ']))):
                in_title_section = False

            if in_title_section:
                # Преобразуем заголовки титульной части в обычный текст
                if line_stripped.startswith('# '):
                    processed_lines.append(line_stripped[2:])  # Убираем #
                elif line_stripped.startswith('## '):
                    processed_lines.append(line_stripped[3:])  # Убираем ##
                elif line_stripped.startswith('### '):
                    processed_lines.append(line_stripped[4:])  # Убираем ###
                else:
                    processed_lines.append(line)
            else:
                processed_lines.append(line)

        return '\n'.join(processed_lines)

    def process_preface_section(self, content: str) -> str:
        """Обрабатывает разделы предисловия, корректируя уровни заголовков"""
        lines = content.split('\n')
        processed_lines = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Корректируем уровни заголовков предисловия
            if line_stripped.startswith('### Предисловие'):
                processed_lines.append('## Предисловие')
            elif line_stripped.startswith('### Сведения о своде правил'):
                processed_lines.append('### Сведения о своде правил')  # Уже правильный уровень
            elif line_stripped.startswith('### Введение'):
                processed_lines.append('## Введение')
            else:
                processed_lines.append(line)

        return '\n'.join(processed_lines)

    def enhance_content_structure(self, content: str) -> str:
        """Улучшает структуру содержимого документа с учетом иерархии"""
        lines = content.split('\n')
        enhanced_lines = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if not line:
                enhanced_lines.append("")
                i += 1
                continue

            # Обработка только размеченных заголовков (#, ##, ###)
            if self._is_marked_header(line):
                # Специальная обработка для предисловия и связанных разделов
                if self._is_preface_related_header(line):
                    enhanced_line = self._process_preface_header(line)
                    enhanced_lines.append(enhanced_line)
                    i += 1
                    continue

                header_level = self._calculate_header_level(line, i, lines)
                enhanced_line = self._format_header_with_level(line, header_level)
                enhanced_lines.append(enhanced_line)
                i += 1
                continue

            # Обработка названий таблиц
            if self._is_table_title(line):
                enhanced_lines.append(f"### {line}")
                i += 1
                continue

            # Обработка приложений
            if self._is_appendix(line):
                enhanced_lines.append(f"## {line}")
                i += 1
                continue

            # Обработка примечаний после таблиц
            if (i > 0 and lines[i - 1].strip() == "--- Таблица конец ---" and
                    self._is_note(line)):
                enhanced_lines.append(line)
                i += 1
                continue

            # Сохраняем оригинальную строку
            enhanced_lines.append(line)
            i += 1

        return '\n'.join(enhanced_lines)

    def _is_preface_related_header(self, line: str) -> bool:
        """Определяет, относится ли заголовок к предисловию"""
        clean_line = re.sub(r'^#+\s+', '', line)
        preface_headers = [
            'Предисловие',
            'Сведения о своде правил',
            'Введение'
        ]
        return any(header in clean_line for header in preface_headers)

    def _process_preface_header(self, line: str) -> str:
        """Обрабатывает заголовки, связанные с предисловием"""
        clean_line = re.sub(r'^#+\s+', '', line)

        if clean_line == 'Предисловие':
            return f"## {clean_line}"
        elif clean_line == 'Сведения о своде правил':
            return f"### {clean_line}"
        elif clean_line == 'Введение':
            return f"## {clean_line}"
        else:
            return line

    def _is_marked_header(self, line: str) -> bool:
        """Определяет, является ли строка размеченным заголовком (#, ##, ###)"""
        return line.startswith('# ') or line.startswith('## ') or line.startswith('### ')

    def _calculate_header_level(self, line: str, current_index: int, all_lines: List[str]) -> int:
        """Вычисляет правильный уровень заголовка на основе нумерации"""
        # Извлекаем чистый текст заголовка (без #)
        clean_line = re.sub(r'^#+\s+', '', line)
        
        # Анализируем структуру нумерации в чистом тексте
        if re.match(r'^\d+\.\d+\.\d+', clean_line):  # 2.1.1 - четвертый уровень
            return 4  # ####
        elif re.match(r'^\d+\.\d+', clean_line):  # 2.1 - третий уровень
            return 3  # ###
        elif re.match(r'^\d+', clean_line):  # 2 - второй уровень
            return 2  # ##
        elif clean_line.startswith('Приложение'):  # Приложения - второй уровень
            return 2  # ##
        else:
            # Для ненумерованных подразделов анализируем контекст
            return self._detect_subsection_level(current_index, all_lines)

    def _detect_subsection_level(self, current_index: int, all_lines: List[str]) -> int:
        """Определяет уровень ненумерованных подразделов по контексту"""
        # Ищем предыдущий заголовок с нумерацией
        for i in range(current_index-1, max(0, current_index-10), -1):
            prev_line = all_lines[i].strip()
            if self._is_marked_header(prev_line):
                clean_prev_line = re.sub(r'^#+\s+', '', prev_line)
                if re.match(r'^\d+\.\d+', clean_prev_line):  # Если предыдущий был 2.1
                    return 4  # То этот должен быть ####
                elif re.match(r'^\d+', clean_prev_line):  # Если предыдущий был 2
                    return 3  # То этот должен быть ###
        
        return 3  # По умолчанию - третий уровень

    def _format_header_with_level(self, line: str, level: int) -> str:
        """Форматирует заголовок с правильным уровнем"""
        markers = ['', '#', '##', '###', '####']
        marker = markers[level] if level < len(markers) else '####'
        
        # Извлекаем чистый текст заголовка
        clean_text = re.sub(r'^#+\s+', '', line)
        return f"{marker} {clean_text}" if marker else clean_text
    
    def _is_table_title(self, line: str) -> bool:
        """Определяет, является ли строка названием таблицы"""
        table_patterns = [
            r'^Таблица\s+\d+[\s\-]',
            r'^Таблица\s+\d+\.\d+[\s\-]',
            r'^TABLE\s+\d+',
        ]
        return any(re.search(pattern, line, re.IGNORECASE) for pattern in table_patterns)
    
    def _is_appendix(self, line: str) -> bool:
        """Определяет, является ли строка приложением"""
        appendix_patterns = [
            r'^Приложение\s+[А-Я]',
            r'^ПРИЛОЖЕНИЕ\s+[А-Я]',
            r'^Appendix\s+[A-Z]',
            r'^APPENDIX\s+[A-Z]',
        ]
        return any(re.search(pattern, line, re.IGNORECASE) for pattern in appendix_patterns)
    
    def _is_note(self, line: str) -> bool:
        """Определяет, является ли строка примечанием"""
        note_indicators = [
            'Примечание',
            'ПРИМЕЧАНИЕ',
            'Note:',
            'NOTE:',
            'Примечания',
            'ПРИМЕЧАНИЯ'
        ]
        return any(indicator in line for indicator in note_indicators)
    
    def add_metadata_section(self, content: str, title: str, metadata: Dict[str, str]) -> str:
        """Добавляет секцию с метаданными в начало документа"""
        metadata_lines = []
        
        # Заголовок документа
        metadata_lines.append(f"# {title}")
        metadata_lines.append("")
        
        # Секция метаданных
        if metadata:
            metadata_lines.append("## Метаданные документа")
            
            if 'code' in metadata:
                metadata_lines.append(f"- **Код документа**: {metadata['code']}")
            if 'title' in metadata:
                metadata_lines.append(f"- **Название**: {metadata['title']}")
            if 'oks' in metadata:
                metadata_lines.append(f"- **ОКС**: {metadata['oks']}")
            if 'okved' in metadata:
                metadata_lines.append(f"- **ОК ВЭД**: {metadata['okved']}")
            if 'date_intro' in metadata:
                metadata_lines.append(f"- **Дата введения**: {metadata['date_intro']}")
            
            metadata_lines.append("")
        
        # Добавляем оригинальное содержимое
        metadata_lines.append(content)
        
        return '\n'.join(metadata_lines)