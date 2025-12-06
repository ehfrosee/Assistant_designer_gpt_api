import fitz  # PyMuPDF
import re
import json
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict
import math


@dataclass
class TextBlock:
    """Структура для хранения текстового блока"""
    text: str
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    page: int
    font_size: float = 0
    font_name: str = ""
    is_bold: bool = False

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2,
                (self.bbox[1] + self.bbox[3]) / 2)

    @property
    def is_in_title_block_area(self) -> bool:
        """Проверка, находится ли блок в области основной надписи (правый нижний угол)"""
        # Обычно штамп в правом нижнем углу
        x0, y0, x1, y1 = self.bbox
        return x0 > 400 and y0 > 700  # Пороговые значения для А4


class DrawingAnalyzer:
    """
    Анализатор чертежей PDF с текстовым слоем
    """

    def __init__(self):
        # Паттерны для поиска информации в чертежах
        self.patterns = {
            'title_block': [
                r'основн[а-я]*\s*надпис[а-я]*',
                r'штамп',
                r'главн[а-я]*\s*надпис[а-я]*',
                r'title\s*block'
            ],
            'object_name': [
                r'(?:наименование\s+)?объекта?[\s:]*([^\n]+)',
                r'объект\s*[№#]?\s*\d*[\s:-]*([^\n]+)',
                r'(?i)объект[:]?\s*(.+)'
            ],
            'drawing_name': [
                r'наименование\s*(?:чертежа)?[\s:]*([^\n]+)',
                r'название\s*(?:чертежа)?[\s:]*([^\n]+)',
                r'чертеж[^\n]*([^\n]+)',
                r'drawing\s*name[\s:]*([^\n]+)'
            ],
            'drawing_number': [
                r'[№#n]\s*[\w\.\-/]+',
                r'чертеж\s*[№#]?\s*([\w\.\-/]+)',
                r'код\s*[\w\.\-/]+',
                r'номер\s*чертежа[\s:]*([\w\.\-/]+)'
            ],
            'developer': [
                r'разраб\.?\s*[:]?\s*([^\n]+)',
                r'разработчик\s*[:]?\s*([^\n]+)',
                r'автор\s*[:]?\s*([^\n]+)',
                r'designed\s*by\s*[:]?\s*([^\n]+)',
                r'исполнитель\s*[:]?\s*([^\n]+)'
            ],
            'checker': [
                r'пров\.?\s*[:]?\s*([^\n]+)',
                r'проверил\s*[:]?\s*([^\n]+)',
                r'контрол[ьё]р\s*[:]?\s*([^\n]+)',
                r'checked\s*by\s*[:]?\s*([^\n]+)'
            ],
            'scale': [
                r'масштаб\s*[:]?\s*([\d\.:\s]+)',
                r'scale\s*[:]?\s*([\d\.:\s]+)'
            ],
            'sheet_number': [
                r'лист\s*[:]?\s*(\d+\s*[из]+\s*\d+)',
                r'листов\s*[:]?\s*(\d+)',
                r'sheet\s*[:]?\s*(\d+\s*of\s*\d+)'
            ]
        }

        # Ключевые слова для разных разделов чертежа
        self.keywords = {
            'title': ['наименование', 'название', 'title', 'name'],
            'specification': ['спецификация', 'specification', 'поз.', 'обозначение'],
            'notes': ['примечание', 'notes', 'указание', 'требования'],
            'dimensions': ['размеры', 'габариты', 'dimensions', 'размер'],
            'materials': ['материал', 'материалы', 'material', 'сталь', 'марка'],
            'revisions': ['изменения', 'исправления', 'revision', 'изм.']
        }

    def extract_text_with_coordinates(self, pdf_path: str) -> List[TextBlock]:
        """
        Извлечение текста с координатами из PDF

        Args:
            pdf_path: Путь к PDF файлу

        Returns:
            Список текстовых блоков с координатами
        """
        doc = fitz.open(pdf_path)
        text_blocks = []

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            # Получаем текст с детальной информацией
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:  # Игнорируем пустые строки
                                bbox = span["bbox"]
                                text_block = TextBlock(
                                    text=text,
                                    bbox=tuple(bbox),
                                    page=page_num + 1,
                                    font_size=span["size"],
                                    font_name=span["font"],
                                    is_bold="bold" in span["font"].lower()
                                )
                                text_blocks.append(text_block)

        doc.close()
        return text_blocks

    def find_title_block_by_layout(self, text_blocks: List[TextBlock]) -> List[TextBlock]:
        """
        Поиск основной надписи по расположению (правый нижний угол)

        Args:
            text_blocks: Все текстовые блоки

        Returns:
            Блоки, относящиеся к основной надписи
        """
        # Группируем по страницам
        blocks_by_page = defaultdict(list)
        for block in text_blocks:
            blocks_by_page[block.page].append(block)

        title_blocks = []

        for page_num, page_blocks in blocks_by_page.items():
            if not page_blocks:
                continue

            # Определяем границы страницы
            page_width = max(b.bbox[2] for b in page_blocks)
            page_height = max(b.bbox[3] for b in page_blocks)

            # Область основной надписи (правый нижний угол)
            title_area = {
                'x_min': page_width * 0.6,  # Правая треть
                'y_min': page_height * 0.7,  # Нижняя треть
                'x_max': page_width,
                'y_max': page_height
            }

            # Ищем блоки в этой области
            for block in page_blocks:
                x0, y0, x1, y1 = block.bbox
                if (x0 >= title_area['x_min'] and y0 >= title_area['y_min'] and
                        x1 <= title_area['x_max'] and y1 <= title_area['y_max']):
                    title_blocks.append(block)

            # Если не нашли по координатам, ищем по ключевым словам
            if not title_blocks:
                for block in page_blocks:
                    text_lower = block.text.lower()
                    if any(pattern in text_lower for pattern in self.patterns['title_block']):
                        title_blocks.append(block)

        return title_blocks

    def analyze_text_relationships(self, text_blocks: List[TextBlock]) -> Dict:
        """
        Анализ пространственных отношений между текстовыми блоками

        Args:
            text_blocks: Все текстовые блоки

        Returns:
            Структурированные данные о расположении текста
        """
        # Группируем блоки по вертикальным колонкам
        columns = self._group_into_columns(text_blocks)

        # Группируем блоки по горизонтальным строкам
        rows = self._group_into_rows(text_blocks)

        # Находим табличные структуры
        tables = self._find_tables(text_blocks)

        return {
            'columns': columns,
            'rows': rows,
            'tables': tables,
            'total_blocks': len(text_blocks),
            'text_density': self._calculate_text_density(text_blocks)
        }

    def _group_into_columns(self, text_blocks: List[TextBlock], threshold: float = 20) -> List[List[TextBlock]]:
        """Группировка блоков в колонки по горизонтальному положению"""
        if not text_blocks:
            return []

        # Сортируем по X координате
        sorted_blocks = sorted(text_blocks, key=lambda b: b.center[0])

        columns = []
        current_column = [sorted_blocks[0]]

        for block in sorted_blocks[1:]:
            # Проверяем, находится ли блок в той же колонке
            last_block = current_column[-1]
            if abs(block.center[0] - last_block.center[0]) < threshold:
                current_column.append(block)
            else:
                columns.append(current_column)
                current_column = [block]

        if current_column:
            columns.append(current_column)

        return columns

    def _group_into_rows(self, text_blocks: List[TextBlock], threshold: float = 10) -> List[List[TextBlock]]:
        """Группировка блоков в строки по вертикальному положению"""
        if not text_blocks:
            return []

        # Сортируем по Y координате
        sorted_blocks = sorted(text_blocks, key=lambda b: b.center[1])

        rows = []
        current_row = [sorted_blocks[0]]

        for block in sorted_blocks[1:]:
            # Проверяем, находится ли блок в той же строке
            last_block = current_row[-1]
            if abs(block.center[1] - last_block.center[1]) < threshold:
                current_row.append(block)
            else:
                rows.append(sorted(current_row, key=lambda b: b.center[0]))
                current_row = [block]

        if current_row:
            rows.append(sorted(current_row, key=lambda b: b.center[0]))

        return rows

    def _find_tables(self, text_blocks: List[TextBlock]) -> List[Dict]:
        """Поиск табличных структур в тексте"""
        tables = []

        # Группируем по страницам
        blocks_by_page = defaultdict(list)
        for block in text_blocks:
            blocks_by_page[block.page].append(block)

        for page_num, page_blocks in blocks_by_page.items():
            rows = self._group_into_rows(page_blocks)

            # Ищем регулярные структуры (таблицы)
            for i in range(len(rows) - 1):
                current_row = rows[i]
                next_row = rows[i + 1]

                # Проверяем, образуют ли строки таблицу
                if (len(current_row) > 1 and len(next_row) > 1 and
                        abs(len(current_row) - len(next_row)) <= 1):

                    # Проверяем вертикальное выравнивание
                    aligned = True
                    for j in range(min(len(current_row), len(next_row))):
                        if abs(current_row[j].center[0] - next_row[j].center[0]) > 50:
                            aligned = False
                            break

                    if aligned:
                        table_data = {
                            'page': page_num,
                            'start_row': i,
                            'end_row': i + 1,
                            'columns': len(current_row),
                            'content': [
                                [block.text for block in current_row],
                                [block.text for block in next_row]
                            ]
                        }
                        tables.append(table_data)

        return tables

    def _calculate_text_density(self, text_blocks: List[TextBlock]) -> Dict:
        """Расчет плотности текста на странице"""
        if not text_blocks:
            return {}

        densities = defaultdict(float)

        for block in text_blocks:
            area = block.width * block.height
            if area > 0:
                density = len(block.text) / area
                densities[block.page] += density

        return dict(densities)

    def extract_structured_info(self, title_blocks: List[TextBlock]) -> Dict:
        """
        Извлечение структурированной информации из основной надписи

        Args:
            title_blocks: Блоки основной надписи

        Returns:
            Структурированная информация
        """
        # Объединяем текст всех блоков
        full_text = "\n".join([block.text for block in title_blocks])

        extracted = {
            'object_name': None,
            'drawing_name': None,
            'drawing_number': None,
            'developers': [],
            'checkers': [],
            'scale': None,
            'sheet_info': None,
            'revisions': [],
            'materials': [],
            'raw_text': full_text
        }

        # Поиск по паттернам
        for field, patterns in self.patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, full_text, re.IGNORECASE)
                for match in matches:
                    if match.groups():
                        value = match.group(1).strip()

                        if field == 'object_name' and not extracted['object_name']:
                            extracted['object_name'] = value
                        elif field == 'drawing_name' and not extracted['drawing_name']:
                            extracted['drawing_name'] = value
                        elif field == 'drawing_number' and not extracted['drawing_number']:
                            extracted['drawing_number'] = value
                        elif field == 'developer':
                            extracted['developers'].append(value)
                        elif field == 'checker':
                            extracted['checkers'].append(value)
                        elif field == 'scale' and not extracted['scale']:
                            extracted['scale'] = value
                        elif field == 'sheet_number' and not extracted['sheet_info']:
                            extracted['sheet_info'] = value

        # Дополнительный анализ для спецификаций
        self._extract_specifications(title_blocks, extracted)

        # Очистка дубликатов
        extracted['developers'] = list(set(extracted['developers']))
        extracted['checkers'] = list(set(extracted['checkers']))

        return extracted

    def _extract_specifications(self, title_blocks: List[TextBlock], extracted: Dict):
        """Извлечение информации из спецификаций (если они в основной надписи)"""
        # Ищем позиции (поз.1, поз.2 и т.д.)
        for block in title_blocks:
            # Поиск обозначений материалов
            material_patterns = [
                r'ст\.\s*[А-Я0-9]+',
                r'ГОСТ\s*\d+',
                r'материал\s*[:]?\s*([^\n]+)'
            ]

            for pattern in material_patterns:
                matches = re.findall(pattern, block.text, re.IGNORECASE)
                extracted['materials'].extend(matches)

    def analyze_drawing_structure(self, text_blocks: List[TextBlock]) -> Dict:
        """
        Анализ общей структуры чертежа

        Args:
            text_blocks: Все текстовые блоки

        Returns:
            Информация о структуре документа
        """
        structure = {
            'title_block': {'found': False, 'blocks': 0, 'area': None},
            'specifications': {'found': False, 'blocks': 0, 'area': None},
            'dimensions': {'found': False, 'blocks': 0},
            'notes': {'found': False, 'blocks': 0},
            'revisions': {'found': False, 'blocks': 0},
            'sections': []
        }

        # Анализ по ключевым словам
        for block in text_blocks:
            text_lower = block.text.lower()

            # Проверка на основную надпись
            if any(keyword in text_lower for keyword in self.patterns['title_block']):
                structure['title_block']['found'] = True
                structure['title_block']['blocks'] += 1

            # Проверка на спецификацию
            if any(keyword in text_lower for keyword in self.keywords['specification']):
                structure['specifications']['found'] = True
                structure['specifications']['blocks'] += 1

            # Проверка на размеры
            if any(keyword in text_lower for keyword in self.keywords['dimensions']):
                structure['dimensions']['found'] = True
                structure['dimensions']['blocks'] += 1

            # Проверка на примечания
            if any(keyword in text_lower for keyword in self.keywords['notes']):
                structure['notes']['found'] = True
                structure['notes']['blocks'] += 1

        # Определение областей по координатам
        if text_blocks:
            # Предполагаем, что чертеж имеет стандартную структуру
            page_width = max(b.bbox[2] for b in text_blocks)
            page_height = max(b.bbox[3] for b in text_blocks)

            structure['page_size'] = {
                'width': page_width,
                'height': page_height,
                'format': self._detect_page_format(page_width, page_height)
            }

        return structure

    def _detect_page_format(self, width: float, height: float) -> str:
        """Определение формата страницы"""
        # Размеры в пунктах (1 пункт = 1/72 дюйма)
        if width > 800 and height > 1100:
            return "A3 или больше"
        elif width > 550 and height > 800:
            return "A4"
        else:
            return "Неизвестный формат"

    def prepare_for_gpt_analysis(self,
                                 extracted_info: Dict,
                                 structure_info: Dict,
                                 relationships: Dict,
                                 text_blocks: List[TextBlock]) -> Dict:
        """
        Подготовка данных для анализа GPT

        Args:
            extracted_info: Извлеченная информация
            structure_info: Структура чертежа
            relationships: Пространственные отношения
            text_blocks: Все текстовые блоки

        Returns:
            Структурированные данные для GPT
        """
        # Группируем текст по разделам
        sections = self._group_text_by_sections(text_blocks)

        gpt_data = {
            'document_type': 'engineering_drawing',
            'summary': {
                'object': extracted_info.get('object_name', 'Не определено'),
                'drawing': extracted_info.get('drawing_name', 'Не определено'),
                'drawing_number': extracted_info.get('drawing_number', 'Не определено'),
                'scale': extracted_info.get('scale', 'Не указан'),
                'total_pages': len(set(b.page for b in text_blocks))
            },
            'personnel': {
                'developers': extracted_info.get('developers', []),
                'checkers': extracted_info.get('checkers', []),
                'approvers': []  # Можно добавить из других полей
            },
            'technical_data': {
                'materials': extracted_info.get('materials', []),
                'specifications': sections.get('specifications', []),
                'notes': sections.get('notes', [])
            },
            'document_structure': {
                'has_title_block': structure_info['title_block']['found'],
                'has_specifications': structure_info['specifications']['found'],
                'has_notes': structure_info['notes']['found'],
                'page_format': structure_info.get('page_size', {}).get('format', 'Неизвестно'),
                'tables_count': len(relationships.get('tables', [])),
                'text_density': relationships.get('text_density', {})
            },
            'content_by_section': sections,
            'spatial_context': {
                'text_blocks_count': len(text_blocks),
                'columns_count': len(relationships.get('columns', [])),
                'tables': relationships.get('tables', [])
            },
            'analysis_prompts': [
                "Проанализируйте технические требования и спецификации",
                "Проверьте наличие всех необходимых разделов чертежа",
                "Оцените полноту информации об объекте",
                "Выявите потенциальные противоречия в данных",
                "Предложите рекомендации по улучшению документации"
            ],
            'raw_context': {
                'title_block_text': extracted_info.get('raw_text', ''),
                'sample_text_blocks': [
                    {
                        'text': block.text[:100] + ('...' if len(block.text) > 100 else ''),
                        'page': block.page,
                        'position': block.center
                    }
                    for block in text_blocks[:10]  # Первые 10 блоков как пример
                ]
            }
        }

        return gpt_data

    def _group_text_by_sections(self, text_blocks: List[TextBlock]) -> Dict:
        """Группировка текста по смысловым разделам"""
        sections = defaultdict(list)

        for block in text_blocks:
            text = block.text
            text_lower = text.lower()

            # Определяем раздел по ключевым словам
            if any(keyword in text_lower for keyword in self.keywords['specification']):
                sections['specifications'].append(text)
            elif any(keyword in text_lower for keyword in self.keywords['notes']):
                sections['notes'].append(text)
            elif any(keyword in text_lower for keyword in self.keywords['materials']):
                sections['materials'].append(text)
            elif any(keyword in text_lower for keyword in self.keywords['dimensions']):
                sections['dimensions'].append(text)
            elif any(keyword in text_lower for keyword in self.keywords['revisions']):
                sections['revisions'].append(text)
            else:
                sections['other'].append(text)

        return dict(sections)

    def process_drawing(self, pdf_path: str) -> Dict:
        """
        Полный процесс обработки чертежа

        Args:
            pdf_path: Путь к PDF файлу

        Returns:
            Результаты анализа
        """
        print(f"Анализ чертежа: {pdf_path}")

        # 1. Извлечение текста с координатами
        print("Извлечение текста...")
        text_blocks = self.extract_text_with_coordinates(pdf_path)

        if not text_blocks:
            raise ValueError("PDF не содержит текста или текст недоступен")

        print(f"Найдено {len(text_blocks)} текстовых блоков")

        # 2. Поиск основной надписи
        print("Поиск основной надписи...")
        title_blocks = self.find_title_block_by_layout(text_blocks)
        print(f"Найдено {len(title_blocks)} блоков в основной надписи")

        # 3. Извлечение структурированной информации
        print("Извлечение информации...")
        extracted_info = self.extract_structured_info(title_blocks)

        # 4. Анализ структуры чертежа
        print("Анализ структуры...")
        structure_info = self.analyze_drawing_structure(text_blocks)

        # 5. Анализ пространственных отношений
        print("Анализ пространственных отношений...")
        relationships = self.analyze_text_relationships(text_blocks)

        # 6. Подготовка для GPT
        print("Подготовка данных для GPT...")
        gpt_data = self.prepare_for_gpt_analysis(
            extracted_info,
            structure_info,
            relationships,
            text_blocks
        )

        results = {
            'file': pdf_path,
            'extracted_info': extracted_info,
            'structure_info': structure_info,
            'text_analysis': {
                'total_blocks': len(text_blocks),
                'title_block_blocks': len(title_blocks),
                'relationships': relationships
            },
            'gpt_ready_data': gpt_data,
            'raw_text_blocks': [
                {
                    'text': block.text,
                    'page': block.page,
                    'bbox': block.bbox,
                    'font_size': block.font_size,
                    'is_bold': block.is_bold
                }
                for block in text_blocks[:50]  # Сохраняем только первые 50 для отладки
            ]
        }

        return results

    def generate_report(self, results: Dict, output_path: str = None):
        """
        Генерация отчета по результатам анализа

        Args:
            results: Результаты анализа
            output_path: Путь для сохранения отчета
        """
        info = results['extracted_info']
        structure = results['structure_info']

        report = f"""
        ОТЧЕТ ПО АНАЛИЗУ ЧЕРТЕЖА
        ========================
        Файл: {results['file']}

        ОСНОВНАЯ ИНФОРМАЦИЯ:
        --------------------
        Объект: {info.get('object_name', 'Не определено')}
        Название чертежа: {info.get('drawing_name', 'Не определено')}
        Номер чертежа: {info.get('drawing_number', 'Не определено')}
        Масштаб: {info.get('scale', 'Не указан')}

        ИСПОЛНИТЕЛИ:
        ------------
        Разработчики: {', '.join(info.get('developers', ['Не указаны']))}
        Проверяющие: {', '.join(info.get('checkers', ['Не указаны']))}

        СТРУКТУРА ДОКУМЕНТА:
        -------------------
        Основная надпись: {'Найдена' if structure['title_block']['found'] else 'Не найдена'}
        Спецификация: {'Найдена' if structure['specifications']['found'] else 'Не найдена'}
        Примечания: {'Найдены' if structure['notes']['found'] else 'Не найдены'}
        Размеры: {'Найдены' if structure['dimensions']['found'] else 'Не найдены'}

        ТЕКСТОВЫЙ АНАЛИЗ:
        -----------------
        Всего текстовых блоков: {results['text_analysis']['total_blocks']}
        Блоков в основной надписи: {results['text_analysis']['title_block_blocks']}
        Найдено таблиц: {len(results['text_analysis']['relationships'].get('tables', []))}

        МАТЕРИАЛЫ:
        ----------
        {chr(10).join(f'  - {mat}' for mat in info.get('materials', [])) if info.get('materials') else '  Не указаны'}
        """

        print(report)

        if output_path:
            # Сохранение полных данных в JSON
            with open(output_path.replace('.txt', '.json'), 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            # Сохранение текстового отчета
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)

            print(f"Отчет сохранен: {output_path}")

        return report


# Пример использования
if __name__ == "__main__":
    # Инициализация анализатора
    analyzer = DrawingAnalyzer()

    # Обработка чертежа
    pdf_file = "path/to/your/drawing.pdf"

    try:
        # Выполнение анализа
        results = analyzer.process_drawing(pdf_file)

        # Генерация отчета
        report = analyzer.generate_report(results, "analysis_report.txt")

        # Пример доступа к данным для GPT
        gpt_data = results['gpt_ready_data']
        print("\nДанные для GPT анализа готовы:")
        print(f"Объект: {gpt_data['summary']['object']}")
        print(f"Разработчики: {', '.join(gpt_data['personnel']['developers'])}")

        # Сохранение структурированных данных
        with open('gpt_analysis_data.json', 'w', encoding='utf-8') as f:
            json.dump(gpt_data, f, ensure_ascii=False, indent=2)

    except FileNotFoundError:
        print(f"Файл не найден: {pdf_file}")
    except ValueError as e:
        print(f"Ошибка анализа: {str(e)}")
    except Exception as e:
        print(f"Неожиданная ошибка: {str(e)}")


# Дополнительные утилиты для работы с текстом чертежей
class DrawingTextUtils:
    """Вспомогательные утилиты для анализа текста чертежей"""

    @staticmethod
    def extract_gost_numbers(text: str) -> List[str]:
        """Извлечение номеров ГОСТ из текста"""
        patterns = [
            r'ГОСТ\s*\d+[\s\-\.]?\d*',
            r'ГОСТ\s*[Р]?\s*\d+[\-\d\.]*',
            r'СТ\s*[А-Я]+\s*\d+'
        ]

        gosts = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            gosts.extend(matches)

        return list(set(gosts))

    @staticmethod
    def extract_dimensions(text: str) -> List[Dict]:
        """Извлечение размеров из текста"""
        # Паттерны для размеров
        patterns = [
            # Числовые размеры
            r'(\d+[.,]?\d*)\s*[×xX*]\s*(\d+[.,]?\d*)\s*[×xX*]?\s*(\d+[.,]?\d*)?',
            r'Ø?\s*(\d+[.,]?\d*)\s*[мМmM]?[мМmM]?',
            r'R\s*(\d+[.,]?\d*)',
            r'\d+[.,]?\d*\s*[мМmM][мМmM]?\s*[xх×]\s*\d+[.,]?\d*\s*[мМmM][мМmM]?'
        ]

        dimensions = []
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                dim = {
                    'text': match.group(0),
                    'values': [v for v in match.groups() if v]
                }
                dimensions.append(dim)

        return dimensions

    @staticmethod
    def normalize_text_blocks(blocks: List[TextBlock]) -> str:
        """Нормализация текстовых блоков в читаемый текст"""
        # Группируем по строкам
        rows = defaultdict(list)
        for block in blocks:
            key = round(block.center[1] / 10) * 10  # Группировка по Y с допуском
            rows[key].append(block)

        # Сортируем строки и блоки в строках
        sorted_text = []
        for y in sorted(rows.keys()):
            row_blocks = sorted(rows[y], key=lambda b: b.center[0])
            row_text = ' | '.join(b.text for b in row_blocks)
            sorted_text.append(row_text)

        return '\n'.join(sorted_text)