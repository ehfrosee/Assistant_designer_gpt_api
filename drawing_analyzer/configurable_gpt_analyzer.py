# configurable_gpt_analyzer.py
import os
import json
import fitz
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
import re
from datetime import datetime
import unicodedata


@dataclass
class TextBlock:
    """Текстовый блок с координатами"""
    text: str
    bbox: Tuple[int, int, int, int]
    page: int
    

@dataclass
class Cluster:
    """Кластер сгруппированных блоков"""
    cluster_id: int
    blocks: List[TextBlock]
    cluster_type: str = "unknown"
    bbox: Optional[Tuple[int, int, int, int]] = None
    text_content: str = ""
    

@dataclass
class PageAnalysis:
    """Анализ отдельной страницы"""
    page_number: int
    width: int
    height: int
    text_blocks: List[Dict]
    clusters: List[Dict]
    tables: List[Dict]
    title_block: Dict
    metadata: Dict
    page_format: Dict
    

@dataclass 
class FileAnalysis:
    """Анализ отдельного файла"""
    file_name: str
    file_type: str
    total_pages: int
    pages: List[PageAnalysis]
    summary: Dict
    relationships: Dict
    file_metadata: Dict


class ConfigurableGPTAnalyzer:
    """Универсальный анализатор с конфигурацией из файла"""
    
    def __init__(self, config_path: str = "config/analyzer_config.json"):
        self.config = self._load_config(config_path)
        self._initialize_from_config()
        self._processed_files = set()
        
    def _normalize_filename(self, filename: str) -> str:
        """Нормализация имени файла для сравнения"""
        normalized = unicodedata.normalize('NFKD', filename.lower())
        return normalized.encode('ASCII', 'ignore').decode('ASCII')
    
    def _load_config(self, config_path: str) -> Dict:
        """Загрузка конфигурации из файла"""
        try:
            config_dir = os.path.dirname(config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"Конфигурационный файл не найден: {config_path}")
                return self._create_default_config(config_path)
        except json.JSONDecodeError as e:
            print(f"Ошибка чтения конфигурации: {e}")
            return self._create_default_config(config_path)
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")
            return self._create_default_config(config_path)
    
    def _create_default_config(self, config_path: str) -> Dict:
        """Создание конфигурации по умолчанию"""
        default_config = {
            "analysis_config": {
                "detect_paper_size": True,
                "extract_metadata": True,
                "find_tables": True,
                "cluster_text_blocks": True,
                "save_detailed_blocks": True,
                "max_blocks_per_page": 500,
                "analysis_depth": "detailed",
                "save_individual_reports": True,
                "reports_output_dir": "data/output/individual_reports"
            },
            "patterns": {
                "title_block_keywords": ["title block", "штамп"],
                "document_type_patterns": {
                    "specification": ["specification", "spec", "спецификация", ".со"],
                    "drawing": ["drawing", "чертеж", "plan", "план"],
                    "scheme": ["scheme", "схема", "диаграмма"]
                },
                "metadata_patterns": {
                    "object_name": ["объект[:\\s]+(.+)", "наименование[:\\s]+(.+)"],
                    "drawing_number": ["[№nN]\\s*([\\w\\-\\.]+)", "обозначение[:\\s]+(.+)"],
                    "scale": ["масштаб[:\\s]+(.+)", "scale[:\\s]+(.+)"],
                    "developer": ["разраб\\.?[:\\s]+(.+)", "исполнитель[:\\s]+(.+)"],
                    "checker": ["пров\\.?[:\\s]+(.+)", "контрол[:\\s]+(.+)"],
                    "company": ["организация[:\\s]+(.+)", "ооо\\s*[«\"](.+?)[»\"]"],
                    "date": ["дата[:\\s]+(\\d{2}[\\./]\\d{2}[\\./]\\d{4})"]
                },
                "system_patterns": ["ПВ\\d+", "П\\d+", "ШУ\\d+"],
                "standard_patterns": ["ГОСТ\\s*\\d+", "СТ\\s*\\d+", "СП\\s*\\d+"],
                "equipment_keywords": ["оборудование", "устройство", "прибор"],
                "table_header_patterns": ["поз\\.", "наименование", "код", "количество"],
                "reference_patterns": ["лист\\s*[№N]?\\s*(\\d+)"]
            },
            "clustering_config": {
                "vertical_threshold": 20.0,
                "horizontal_threshold": 50.0,
                "table_row_threshold": 10.0,
                "min_table_rows": 2,
                "min_table_columns": 2
            },
            "output_config": {
                "default_output_file": "data/output/project_analysis.json",
                "encoding": "utf-8",
                "indent": 2,
                "ensure_ascii": False,
                "compress_output": False
            }
        }
        
        try:
            config_dir = os.path.dirname(config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            print(f"Создана конфигурация по умолчанию: {config_path}")
        except Exception as e:
            print(f"Ошибка сохранения конфигурации по умолчанию: {e}")
        
        return default_config
    
    def _initialize_from_config(self):
        """Инициализация параметров из конфигурации"""
        try:
            self.analysis_config = self.config.get("analysis_config", {})
            self.detect_paper_size = self.analysis_config.get("detect_paper_size", True)
            self.extract_metadata = self.analysis_config.get("extract_metadata", True)
            self.find_tables = self.analysis_config.get("find_tables", True)
            self.cluster_text_blocks = self.analysis_config.get("cluster_text_blocks", True)
            self.save_detailed_blocks = self.analysis_config.get("save_detailed_blocks", True)
            self.max_blocks_per_page = self.analysis_config.get("max_blocks_per_page", 500)
            self.analysis_depth = self.analysis_config.get("analysis_depth", "detailed")
            self.save_individual_reports = self.analysis_config.get("save_individual_reports", True)
            self.reports_output_dir = self.analysis_config.get("reports_output_dir", "data/output/individual_reports")
            
            patterns = self.config.get("patterns", {})
            self.title_keywords = patterns.get("title_block_keywords", [])
            self.document_type_patterns = patterns.get("document_type_patterns", {})
            self.metadata_patterns = patterns.get("metadata_patterns", {})
            self.system_patterns = patterns.get("system_patterns", [])
            self.standard_patterns = patterns.get("standard_patterns", [])
            self.equipment_keywords = patterns.get("equipment_keywords", [])
            self.table_header_patterns = patterns.get("table_header_patterns", [])
            self.reference_patterns = patterns.get("reference_patterns", [])
            
            clustering = self.config.get("clustering_config", {})
            self.vertical_threshold = clustering.get("vertical_threshold", 20.0)
            self.horizontal_threshold = clustering.get("horizontal_threshold", 50.0)
            self.table_row_threshold = clustering.get("table_row_threshold", 10.0)
            self.min_table_rows = clustering.get("min_table_rows", 2)
            self.min_table_columns = clustering.get("min_table_columns", 2)
            
            output_config = self.config.get("output_config", {})
            self.default_output_file = output_config.get("default_output_file", "gpt_analysis.json")
            self.output_encoding = output_config.get("encoding", "utf-8")
            self.output_indent = output_config.get("indent", 2)
            self.output_ensure_ascii = output_config.get("ensure_ascii", False)
            self.compress_output = output_config.get("compress_output", False)
            
        except Exception as e:
            print(f"Ошибка инициализации конфигурации: {e}")
            self._set_default_values()
    
    def _set_default_values(self):
        """Установка значений по умолчанию при ошибке конфигурации"""
        self.detect_paper_size = True
        self.extract_metadata = True
        self.find_tables = True
        self.cluster_text_blocks = True
        self.save_detailed_blocks = True
        self.max_blocks_per_page = 500
        self.analysis_depth = "detailed"
        self.save_individual_reports = True
        self.reports_output_dir = "data/output/individual_reports"
        
        self.title_keywords = ["title block", "штамп"]
        self.document_type_patterns = {
            "specification": ["specification", "spec", "спецификация", ".со"],
            "drawing": ["drawing", "чертеж"],
            "scheme": ["scheme", "схема"]
        }
        self.metadata_patterns = {
            "object_name": ["объект[:\\s]+(.+)", "наименование[:\\s]+(.+)"],
            "drawing_number": ["[№nN]\\s*([\\w\\-\\.]+)", "обозначение[:\\s]+(.+)"]
        }
        self.system_patterns = ["ПВ\\d+", "П\\d+", "ШУ\\d+"]
        self.standard_patterns = ["ГОСТ\\s*\\d+", "СТ\\s*\\d+", "СП\\s*\\d+"]
        self.equipment_keywords = ["оборудование", "устройство"]
        self.table_header_patterns = ["поз\\.", "наименование"]
        self.reference_patterns = ["лист\\s*[№N]?\\s*(\\d+)"]
        
        self.vertical_threshold = 20.0
        self.horizontal_threshold = 50.0
        self.table_row_threshold = 10.0
        self.min_table_rows = 2
        self.min_table_columns = 2
        
        self.default_output_file = "gpt_analysis.json"
        self.output_encoding = "utf-8"
        self.output_indent = 2
        self.output_ensure_ascii = False
        self.compress_output = False
    
    def analyze_pdf_files(self, pdf_folder: str, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Анализ всех PDF файлов в папке с сохранением отдельных отчётов"""
        pdf_files = self._find_pdf_files(pdf_folder)
        
        if not pdf_files:
            raise ValueError(f"Не найдены PDF файлы в папке: {pdf_folder}")
        
        self._processed_files.clear()
        
        analysis_results = {
            "analysis_timestamp": datetime.now().isoformat(),
            "configuration_used": {
                "analysis_config": self.analysis_config,
                "clustering_config": {
                    "vertical_threshold": self._round_int(self.vertical_threshold),
                    "horizontal_threshold": self._round_int(self.horizontal_threshold)
                }
            },
            "total_files": len(pdf_files),
            "files": [],
            "project_summary": {},
            "cross_references": [],
            "individual_reports": []
        }
        
        all_files_data = []
        
        for pdf_file in pdf_files:
            file_key = self._normalize_filename(pdf_file.name)
            if file_key in self._processed_files:
                print(f"Пропуск дубликата: {pdf_file.name}")
                continue
                
            print(f"\nАнализ файла: {pdf_file.name}")
            try:
                file_analysis = self.analyze_single_file(str(pdf_file))
                all_files_data.append(file_analysis)
                
                file_dict = self._file_analysis_to_dict(file_analysis)
                analysis_results["files"].append(file_dict)
                
                # Сохраняем отдельный отчёт для этого файла
                if self.save_individual_reports:
                    report_path = self._save_individual_report(file_analysis, pdf_file.name)
                    analysis_results["individual_reports"].append({
                        "file_name": pdf_file.name,
                        "report_path": report_path
                    })
                
                self._processed_files.add(file_key)
                
            except Exception as e:
                print(f"Ошибка анализа файла {pdf_file.name}: {str(e)}")
                continue
        
        if not all_files_data:
            raise ValueError("Не удалось проанализировать ни одного файла")
        
        analysis_results["total_files"] = len(all_files_data)
        analysis_results["project_summary"] = self._create_project_summary(all_files_data)
        
        if len(all_files_data) > 1:
            analysis_results["cross_references"] = self._find_cross_references(all_files_data)
        
        output_path = output_file or self.default_output_file
        self._save_analysis_results(analysis_results, output_path)
        
        return analysis_results
    
    def _save_individual_report(self, file_analysis: FileAnalysis, original_filename: str) -> str:
        """Сохранение отдельного отчёта для каждого файла"""
        os.makedirs(self.reports_output_dir, exist_ok=True)
        
        base_name = os.path.splitext(original_filename)[0]
        safe_name = re.sub(r'[^\w\-_\. ]', '_', base_name)
        report_filename = f"{safe_name}_analysis.json"
        report_path = os.path.join(self.reports_output_dir, report_filename)
        
        report_data = {
            "analysis_timestamp": datetime.now().isoformat(),
            "original_file": original_filename,
            "file_analysis": self._file_analysis_to_dict(file_analysis),
            "statistics": self._create_file_statistics(file_analysis)
        }
        
        with open(report_path, 'w', encoding=self.output_encoding) as f:
            if self.compress_output:
                json.dump(report_data, f, ensure_ascii=self.output_ensure_ascii)
            else:
                json.dump(report_data, f, ensure_ascii=self.output_ensure_ascii, 
                         indent=self.output_indent)
        
        print(f"  Отчёт сохранён: {report_path}")
        return report_path
    
    def _create_file_statistics(self, file_analysis: FileAnalysis) -> Dict:
        """Создание статистики для отдельного файла"""
        stats = {
            "total_pages": file_analysis.total_pages,
            "total_text_blocks": sum(len(page.text_blocks) for page in file_analysis.pages),
            "total_clusters": sum(len(page.clusters) for page in file_analysis.pages),
            "total_tables": sum(len(page.tables) for page in file_analysis.pages),
            "pages_with_title_block": sum(1 for page in file_analysis.pages if page.title_block.get("found")),
            "unique_systems": set(),
            "unique_standards": set(),
            "page_formats": {}
        }
        
        for page in file_analysis.pages:
            stats["unique_systems"].update(page.metadata.get("system_references", []))
            stats["unique_standards"].update(page.metadata.get("standard_references", []))
            
            page_format = page.page_format.get("format", "unknown")
            stats["page_formats"][page_format] = stats["page_formats"].get(page_format, 0) + 1
        
        stats["unique_systems"] = list(stats["unique_systems"])
        stats["unique_standards"] = list(stats["unique_standards"])
        
        return stats
    
    def _round_int(self, value: float) -> int:
        if value is None:
            return 0
        return int(round(float(value)))
    
    def _round_bbox(self, bbox: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
        if not bbox or len(bbox) != 4:
            return (0, 0, 0, 0)
        return tuple(self._round_int(x) for x in bbox)
    
    def _find_pdf_files(self, folder: str) -> List[Path]:
        """Поиск PDF файлов с улучшенной обработкой"""
        pdf_extensions = ['.pdf', '.PDF']
        pdf_files = []
        seen_files = set()
        
        for ext in pdf_extensions:
            for file_path in Path(folder).glob(f"*{ext}"):
                try:
                    file_key = self._normalize_filename(file_path.name)
                    if file_key not in seen_files:
                        seen_files.add(file_key)
                        pdf_files.append(file_path)
                except Exception as e:
                    print(f"Ошибка обработки файла {file_path}: {e}")
                    continue
        
        return sorted(pdf_files, key=lambda x: x.name.lower())
    
    def analyze_single_file(self, pdf_path: str) -> FileAnalysis:
        """Анализ одного PDF файла с улучшенной обработкой ошибок"""
        try:
            doc = fitz.open(pdf_path)
            file_name = os.path.basename(pdf_path)
            
            try:
                file_type = self._determine_file_type(file_name, doc)
                pages_analysis = []
                
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    page_analysis = self._analyze_page(page, page_num)
                    pages_analysis.append(page_analysis)
                
            finally:
                doc.close()
            
            summary = self._create_file_summary(pages_analysis, file_type)
            relationships = self._analyze_relationships(pages_analysis)
            file_metadata = self._extract_file_metadata(pages_analysis, file_name)
            
            return FileAnalysis(
                file_name=file_name,
                file_type=file_type,
                total_pages=len(pages_analysis),
                pages=pages_analysis,
                summary=summary,
                relationships=relationships,
                file_metadata=file_metadata
            )
            
        except Exception as e:
            print(f"Ошибка при анализе файла {pdf_path}: {e}")
            raise
    
    def _analyze_page(self, page, page_num: int) -> PageAnalysis:
        """Анализ отдельной страницы"""
        try:
            width = self._round_int(page.rect.width)
            height = self._round_int(page.rect.height)
            
            text_blocks = self._extract_text_blocks(page, page_num)
            
            page_format = {}
            if self.detect_paper_size:
                page_format = self._detect_page_format(width, height)
            
            clusters = []
            if self.cluster_text_blocks and text_blocks:
                clusters = self._cluster_blocks(text_blocks)
            
            tables = []
            if self.find_tables and text_blocks:
                tables = self._find_tables(text_blocks)
            
            title_block = self._find_title_block(text_blocks)
            
            metadata = {}
            if self.extract_metadata and text_blocks:
                metadata = self._extract_metadata_from_blocks(text_blocks)
            
            blocks_dict = []
            if self.save_detailed_blocks and text_blocks:
                blocks_dict = [self._block_to_dict(b) for b in text_blocks[:self.max_blocks_per_page]]
            
            return PageAnalysis(
                page_number=page_num + 1,
                width=width,
                height=height,
                text_blocks=blocks_dict,
                clusters=[self._cluster_to_dict(c) for c in clusters],
                tables=tables,
                title_block=title_block,
                metadata=metadata,
                page_format=page_format
            )
        except Exception as e:
            print(f"Ошибка анализа страницы {page_num + 1}: {e}")
            return PageAnalysis(
                page_number=page_num + 1,
                width=0,
                height=0,
                text_blocks=[],
                clusters=[],
                tables=[],
                title_block={"found": False},
                metadata={},
                page_format={}
            )
    
    def _extract_text_blocks(self, page, page_num: int) -> List[TextBlock]:
        """Извлечение текстовых блоков с улучшенной обработкой"""
        blocks = []
        
        try:
            text_dict = page.get_text("dict")
            
            for block in text_dict.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                rounded_bbox = self._round_bbox(tuple(span["bbox"]))
                                
                                text_block = TextBlock(
                                    text=text,
                                    bbox=rounded_bbox,
                                    page=page_num + 1
                                )
                                blocks.append(text_block)
        except Exception as e:
            print(f"Ошибка извлечения текстовых блоков на странице {page_num + 1}: {e}")
        
        return blocks
    
    def _cluster_blocks(self, blocks: List[TextBlock]) -> List[Cluster]:
        """Группировка блоков по близости"""
        if not blocks:
            return []
        
        sorted_blocks = sorted(blocks, key=lambda b: b.bbox[1])
        clusters = []
        current_cluster_blocks = [sorted_blocks[0]]
        current_cluster_id = 1
        
        for i in range(1, len(sorted_blocks)):
            prev_block = sorted_blocks[i-1]
            curr_block = sorted_blocks[i]
            
            vertical_dist = curr_block.bbox[1] - prev_block.bbox[3]
            
            if vertical_dist < self.vertical_threshold:
                current_cluster_blocks.append(curr_block)
            else:
                if current_cluster_blocks:
                    cluster = self._create_cluster(current_cluster_blocks, current_cluster_id)
                    clusters.append(cluster)
                    current_cluster_id += 1
                current_cluster_blocks = [curr_block]
        
        if current_cluster_blocks:
            cluster = self._create_cluster(current_cluster_blocks, current_cluster_id)
            clusters.append(cluster)
        
        return clusters
    
    def _create_cluster(self, blocks: List[TextBlock], cluster_id: int) -> Cluster:
        """Создание кластера из группы блоков"""
        if not blocks:
            return Cluster(cluster_id=cluster_id, blocks=[])
        
        x0 = min(b.bbox[0] for b in blocks)
        y0 = min(b.bbox[1] for b in blocks)
        x1 = max(b.bbox[2] for b in blocks)
        y1 = max(b.bbox[3] for b in blocks)
        
        rounded_bbox = (x0, y0, x1, y1)
        text_content = " ".join([b.text for b in blocks])
        
        return Cluster(
            cluster_id=cluster_id,
            blocks=blocks,
            cluster_type="cluster",
            bbox=rounded_bbox,
            text_content=text_content
        )
    
    def _find_tables(self, blocks: List[TextBlock]) -> List[Dict]:
        """Поиск табличных структур"""
        tables = []
        
        rows = self._group_into_rows(blocks, self.table_row_threshold)
        
        for i in range(len(rows) - self.min_table_rows + 1):
            candidate_rows = rows[i:i + self.min_table_rows]
            
            if all(len(row) >= self.min_table_columns for row in candidate_rows):
                if self._check_column_alignment(candidate_rows):
                    table_blocks = []
                    for row in candidate_rows:
                        table_blocks.extend(row)
                    
                    table_info = {
                        "start_row": i,
                        "row_count": len(candidate_rows),
                        "column_count": len(candidate_rows[0]),
                        "content": [[b.text for b in row] for row in candidate_rows],
                        "bbox": self._calculate_bbox(table_blocks)
                    }
                    tables.append(table_info)
        
        return tables
    
    def _group_into_rows(self, blocks: List[TextBlock], threshold: float) -> List[List[TextBlock]]:
        """Группировка блоков в строки"""
        if not blocks:
            return []
        
        sorted_blocks = sorted(blocks, key=lambda b: b.bbox[1])
        rows = []
        current_row = [sorted_blocks[0]]
        
        for block in sorted_blocks[1:]:
            last_block = current_row[-1]
            y1_last = last_block.bbox[3]
            y0_curr = block.bbox[1]
            
            if abs(y0_curr - y1_last) < threshold:
                current_row.append(block)
            else:
                rows.append(sorted(current_row, key=lambda b: b.bbox[0]))
                current_row = [block]
        
        if current_row:
            rows.append(sorted(current_row, key=lambda b: b.bbox[0]))
        
        return rows
    
    def _check_column_alignment(self, rows: List[List[TextBlock]]) -> bool:
        """Проверка выравнивания колонок между строками"""
        if not rows or len(rows) < 2:
            return False
        
        col_count = len(rows[0])
        if not all(len(row) == col_count for row in rows[1:]):
            return False
        
        for col_idx in range(col_count):
            centers = []
            for row in rows:
                if col_idx < len(row):
                    block = row[col_idx]
                    center = (block.bbox[0] + block.bbox[2]) / 2
                    centers.append(center)
            
            if centers and max(centers) - min(centers) > self.horizontal_threshold:
                return False
        
        return True
    
    def _calculate_bbox(self, blocks: List[TextBlock]) -> Dict:
        """Вычисление границ группы блоков"""
        if not blocks:
            return {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "width": 0, "height": 0}
        
        x0 = min(b.bbox[0] for b in blocks)
        y0 = min(b.bbox[1] for b in blocks)
        x1 = max(b.bbox[2] for b in blocks)
        y1 = max(b.bbox[3] for b in blocks)
        
        width = x1 - x0
        height = y1 - y0
        
        return {
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "width": width,
            "height": height
        }
    
    def _detect_page_format(self, width: int, height: int) -> Dict:
        """Определение формата страницы"""
        standard_formats = {
            'A4': {'width': 595, 'height': 842},
            'A3': {'width': 842, 'height': 1191},
            'A2': {'width': 1191, 'height': 1684},
            'A1': {'width': 1684, 'height': 2384},
            'A0': {'width': 2384, 'height': 3370}
        }
        
        is_landscape = width > height
        short_side = min(width, height)
        long_side = max(width, height)
        
        best_match = None
        min_error = float('inf')
        
        for format_name, size in standard_formats.items():
            error_book = abs(short_side - size['width']) + abs(long_side - size['height'])
            error_landscape = abs(short_side - size['height']) + abs(long_side - size['width'])
            
            if error_book < min_error:
                min_error = error_book
                best_match = {
                    'format': format_name,
                    'orientation': 'book',
                    'error': error_book
                }
            
            if error_landscape < min_error:
                min_error = error_landscape
                best_match = {
                    'format': format_name,
                    'orientation': 'landscape',
                    'error': error_landscape
                }
        
        if best_match and min_error < 50:
            best_match['detected_width'] = short_side if not is_landscape else long_side
            best_match['detected_height'] = long_side if not is_landscape else short_side
            best_match['width_mm'] = self._round_int(best_match['detected_width'] * 25.4 / 72)
            best_match['height_mm'] = self._round_int(best_match['detected_height'] * 25.4 / 72)
            return best_match
        
        return {
            'format': 'custom',
            'orientation': 'landscape' if is_landscape else 'book',
            'width_pt': width,
            'height_pt': height,
            'width_mm': self._round_int(width * 25.4 / 72),
            'height_mm': self._round_int(height * 25.4 / 72)
        }
    
    def _find_title_block(self, blocks: List[TextBlock]) -> Dict:
        """Поиск основной надписи"""
        if blocks:
            page_width = max(b.bbox[2] for b in blocks)
            page_height = max(b.bbox[3] for b in blocks)
            
            corner_blocks = []
            for block in blocks:
                x0, y0, _, _ = block.bbox
                if x0 > page_width * 0.6 and y0 > page_height * 0.7:
                    corner_blocks.append(block)
            
            if corner_blocks:
                bbox = self._calculate_bbox(corner_blocks)
                text_content = " ".join([b.text for b in corner_blocks])
                
                return {
                    "found": True,
                    "method": "corner_detection",
                    "block_count": len(corner_blocks),
                    "bbox": bbox,
                    "text_content": text_content,
                    "metadata": self._parse_metadata_from_text(text_content)
                }
        
        return {
            "found": False,
            "method": "none",
            "block_count": 0,
            "bbox": {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "width": 0, "height": 0},
            "text_content": "",
            "metadata": {}
        }
    
    def _parse_metadata_from_text(self, text: str) -> Dict:
        """Парсинг метаданных из текста с улучшенной обработкой Unicode"""
        metadata = {}
        
        for field in self.metadata_patterns.keys():
            if field.endswith('s'):
                metadata[field] = []
            else:
                metadata[field] = ""
        
        text_normalized = unicodedata.normalize('NFKD', text)
        
        for field, patterns in self.metadata_patterns.items():
            for pattern in patterns:
                try:
                    matches = re.finditer(pattern, text_normalized, re.UNICODE | re.IGNORECASE)
                    for match in matches:
                        if match.groups():
                            value = match.group(1).strip()
                            if value:
                                if field.endswith('s'):
                                    if value not in metadata[field]:
                                        metadata[field].append(value)
                                elif not metadata[field]:
                                    metadata[field] = value
                except re.error as e:
                    print(f"Ошибка в паттерне {pattern}: {e}")
                    continue
        
        return metadata
    
    def _extract_metadata_from_blocks(self, blocks: List[TextBlock]) -> Dict:
        """Извлечение метаданных из блоков страницы"""
        metadata = {
            "system_references": [],
            "standard_references": [],
            "equipment_keywords": [],
            "frequent_terms": []
        }
        
        all_text = " ".join([b.text for b in blocks])
        all_text_normalized = unicodedata.normalize('NFKD', all_text)
        
        # Поиск системных обозначений
        for pattern in self.system_patterns:
            try:
                matches = re.findall(pattern, all_text_normalized, re.UNICODE)
                metadata["system_references"].extend(matches)
            except re.error as e:
                print(f"Ошибка в паттерне систем: {pattern}: {e}")
                continue
        
        metadata["system_references"] = list(set(metadata["system_references"]))
        
        # Поиск стандартов
        for pattern in self.standard_patterns:
            try:
                matches = re.findall(pattern, all_text_normalized, re.UNICODE)
                metadata["standard_references"].extend(matches)
            except re.error as e:
                print(f"Ошибка в паттерне стандартов: {pattern}: {e}")
                continue
        
        metadata["standard_references"] = list(set(metadata["standard_references"]))
        
        # Поиск ключевых слов оборудования
        for keyword in self.equipment_keywords:
            keyword_normalized = unicodedata.normalize('NFKD', keyword.lower())
            if keyword_normalized in all_text_normalized.lower():
                metadata["equipment_keywords"].append(keyword)
        
        # Частые термины
        words = re.findall(r'\b[\wА-Яа-я]{4,}\b', all_text, re.UNICODE)
        word_counts = {}
        
        for word in words:
            word_lower = unicodedata.normalize('NFKD', word.lower())
            if (len(word_lower) > 3 and 
                word_lower not in [unicodedata.normalize('NFKD', k.lower()) for k in self.equipment_keywords]):
                word_counts[word_lower] = word_counts.get(word_lower, 0) + 1
        
        sorted_terms = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        metadata["frequent_terms"] = [term for term, count in sorted_terms if count >= 2]
        
        return metadata
    
    def _determine_file_type(self, filename: str, doc) -> str:
        """Определение типа файла"""
        filename_lower = filename.lower()
        
        # Проверяем паттерны типов документов
        for doc_type, patterns in self.document_type_patterns.items():
            for pattern in patterns:
                if pattern.lower() in filename_lower:
                    return doc_type
        
        # Если не определили по имени файла, анализируем содержимое
        try:
            if len(doc) > 0:
                page = doc.load_page(0)
                page_text = page.get_text().lower()
                
                for doc_type, patterns in self.document_type_patterns.items():
                    for pattern in patterns:
                        if pattern.lower() in page_text:
                            return doc_type
        except:
            pass
        
        return "document"
    
    def _create_file_summary(self, pages_analysis: List[PageAnalysis], file_type: str) -> Dict:
        """Создание сводки по файлу"""
        summary = {
            "file_type": file_type,
            "total_pages": len(pages_analysis),
            "pages_with_title_block": 0,
            "total_tables": 0,
            "total_clusters": 0,
            "unique_systems": set(),
            "unique_standards": set(),
            "page_formats": {}
        }
        
        for page in pages_analysis:
            if page.title_block.get("found"):
                summary["pages_with_title_block"] += 1
            
            summary["total_tables"] += len(page.tables)
            summary["total_clusters"] += len(page.clusters)
            
            summary["unique_systems"].update(page.metadata.get("system_references", []))
            summary["unique_standards"].update(page.metadata.get("standard_references", []))
            
            page_format = page.page_format.get("format", "unknown")
            summary["page_formats"][page_format] = summary["page_formats"].get(page_format, 0) + 1
        
        summary["unique_systems"] = list(summary["unique_systems"])
        summary["unique_standards"] = list(summary["unique_standards"])
        
        return summary
    
    def _analyze_relationships(self, pages_analysis: List[PageAnalysis]) -> Dict:
        """Анализ связей между страницами"""
        relationships = {
            "page_references": [],
            "system_distribution": {},
            "metadata_consistency": True
        }
        
        if len(pages_analysis) < 2:
            return relationships
        
        for i, page in enumerate(pages_analysis):
            page_text = " ".join([block["text"] for block in page.text_blocks])
            
            for pattern in self.reference_patterns:
                try:
                    matches = re.findall(pattern, page_text, re.IGNORECASE | re.UNICODE)
                    for match in matches:
                        try:
                            ref_page = int(match)
                            if 1 <= ref_page <= len(pages_analysis) and ref_page != i + 1:
                                relationships["page_references"].append({
                                    "from_page": i + 1,
                                    "to_page": ref_page,
                                    "reference": match
                                })
                        except ValueError:
                            continue
                except re.error as e:
                    print(f"Ошибка в паттерне ссылок: {pattern}: {e}")
                    continue
        
        for i, page in enumerate(pages_analysis):
            systems = page.metadata.get("system_references", [])
            if systems:
                relationships["system_distribution"][i + 1] = systems
        
        if pages_analysis:
            first_title_meta = None
            for page in pages_analysis:
                if page.title_block.get("found"):
                    meta = page.title_block.get("metadata", {})
                    if first_title_meta is None:
                        first_title_meta = meta
                    else:
                        for key in ["drawing_number", "object_name"]:
                            if (key in first_title_meta and key in meta and
                                first_title_meta[key] and meta[key] and
                                first_title_meta[key] != meta[key]):
                                relationships["metadata_consistency"] = False
                                break
        
        return relationships
    
    def _extract_file_metadata(self, pages_analysis: List[PageAnalysis], filename: str) -> Dict:
        """Извлечение метаданных файла"""
        file_metadata = {
            "filename": filename,
            "title_block_present": False,
            "document_info": {}
        }
        
        for page in pages_analysis:
            if page.title_block.get("found"):
                file_metadata["title_block_present"] = True
                if not file_metadata["document_info"]:
                    file_metadata["document_info"] = page.title_block.get("metadata", {})
                break
        
        return file_metadata
    
    def _create_project_summary(self, files_analysis: List[FileAnalysis]) -> Dict:
        """Создание сводки по проекту"""
        summary = {
            "total_files": len(files_analysis),
            "total_pages": sum(f.total_pages for f in files_analysis),
            "file_type_distribution": {},
            "all_systems": set(),
            "all_standards": set(),
            "document_personnel": {
                "developers": set(),
                "checkers": set(),
                "organizations": set()
            },
            "document_numbers": set()
        }
        
        for file_analysis in files_analysis:
            file_type = file_analysis.file_type
            summary["file_type_distribution"][file_type] = summary["file_type_distribution"].get(file_type, 0) + 1
            
            for page in file_analysis.pages:
                summary["all_systems"].update(page.metadata.get("system_references", []))
                summary["all_standards"].update(page.metadata.get("standard_references", []))
                
                if page.title_block.get("found"):
                    meta = page.title_block.get("metadata", {})
                    
                    if "developers" in meta:
                        for dev in meta["developers"]:
                            if dev:
                                summary["document_personnel"]["developers"].add(dev)
                    
                    if "checkers" in meta:
                        for checker in meta["checkers"]:
                            if checker:
                                summary["document_personnel"]["checkers"].add(checker)
                    
                    if "company" in meta and meta["company"]:
                        summary["document_personnel"]["organizations"].add(meta["company"])
                    
                    if "drawing_number" in meta and meta["drawing_number"]:
                        summary["document_numbers"].add(meta["drawing_number"])
        
        summary["all_systems"] = list(summary["all_systems"])
        summary["all_standards"] = list(summary["all_standards"])
        summary["document_numbers"] = list(summary["document_numbers"])
        
        for key in summary["document_personnel"]:
            summary["document_personnel"][key] = list(summary["document_personnel"][key])
        
        return summary
    
    def _find_cross_references(self, files_analysis: List[FileAnalysis]) -> List[Dict]:
        """Поиск перекрестных ссылок между файлами"""
        cross_refs = []
        
        if len(files_analysis) < 2:
            return cross_refs
        
        systems_by_file = {}
        
        for i, file_analysis in enumerate(files_analysis):
            file_systems = set()
            for page in file_analysis.pages:
                file_systems.update(page.metadata.get("system_references", []))
            
            systems_by_file[file_analysis.file_name] = {
                "index": i,
                "systems": file_systems,
                "type": file_analysis.file_type
            }
        
        file_names = list(systems_by_file.keys())
        
        for i in range(len(file_names)):
            for j in range(i + 1, len(file_names)):
                file1_info = systems_by_file[file_names[i]]
                file2_info = systems_by_file[file_names[j]]
                
                common_systems = file1_info["systems"].intersection(file2_info["systems"])
                
                if common_systems:
                    cross_refs.append({
                        "file1": file_names[i],
                        "file2": file_names[j],
                        "file1_type": file1_info["type"],
                        "file2_type": file2_info["type"],
                        "common_systems": list(common_systems),
                        "common_count": len(common_systems)
                    })
        
        return cross_refs
    
    def _block_to_dict(self, block: TextBlock) -> Dict:
        """Конвертация TextBlock в словарь"""
        return {
            "text": block.text,
            "bbox": block.bbox,
            "page": block.page
        }
    
    def _cluster_to_dict(self, cluster: Cluster) -> Dict:
        """Конвертация Cluster в словарь"""
        return {
            "cluster_id": cluster.cluster_id,
            "bbox": cluster.bbox if cluster.bbox else (0, 0, 0, 0),
            "text_content": cluster.text_content,
            "block_count": len(cluster.blocks),
            "blocks": [self._block_to_dict(b) for b in cluster.blocks[:5]] if cluster.blocks else []
        }
    
    def _file_analysis_to_dict(self, file_analysis: FileAnalysis) -> Dict:
        """Конвертация FileAnalysis в словарь"""
        return {
            "file_name": file_analysis.file_name,
            "file_type": file_analysis.file_type,
            "total_pages": file_analysis.total_pages,
            "pages": [self._page_analysis_to_dict(p) for p in file_analysis.pages],
            "summary": file_analysis.summary,
            "relationships": file_analysis.relationships,
            "file_metadata": file_analysis.file_metadata
        }
    
    def _page_analysis_to_dict(self, page_analysis: PageAnalysis) -> Dict:
        """Конвертация PageAnalysis в словарь"""
        return {
            "page_number": page_analysis.page_number,
            "width": page_analysis.width,
            "height": page_analysis.height,
            "text_blocks_count": len(page_analysis.text_blocks),
            "clusters": page_analysis.clusters,
            "tables": page_analysis.tables,
            "title_block": page_analysis.title_block,
            "metadata": page_analysis.metadata,
            "page_format": self._round_page_format(page_analysis.page_format)
        }
    
    def _round_page_format(self, page_format: Dict) -> Dict:
        """Округление числовых значений в формате страницы"""
        rounded_format = {}
        for key, value in page_format.items():
            if isinstance(value, (int, float)):
                rounded_format[key] = self._round_int(value)
            else:
                rounded_format[key] = value
        return rounded_format
    
    def _save_analysis_results(self, results: Dict, output_path: str):
        """Сохранение результатов анализа"""
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            with open(output_path, 'w', encoding=self.output_encoding) as f:
                if self.compress_output:
                    json.dump(results, f, ensure_ascii=self.output_ensure_ascii)
                else:
                    json.dump(results, f, ensure_ascii=self.output_ensure_ascii, 
                             indent=self.output_indent)
            
            print(f"\nРезультаты анализа сохранены в: {output_path}")
            self._print_statistics(results)
            
        except Exception as e:
            print(f"Ошибка сохранения результатов: {e}")
    
    def _print_statistics(self, results: Dict):
        """Вывод статистики анализа"""
        print("\n" + "="*60)
        print("СТАТИСТИКА АНАЛИЗА")
        print("="*60)
        
        print(f"Всего файлов: {results['total_files']}")
        print(f"Всего страниц: {results['project_summary']['total_pages']}")
        
        if results.get('individual_reports'):
            print(f"\nСоздано отдельных отчётов: {len(results['individual_reports'])}")
            for report in results['individual_reports']:
                print(f"  • {report['file_name']} -> {report['report_path']}")
        
        if results['files']:
            print(f"\nПроанализированные файлы:")
            for file_info in results['files']:
                print(f"  • {file_info['file_name']} "
                      f"({file_info['file_type']}, {file_info['total_pages']} стр.)")
        
        if results['project_summary']['all_systems']:
            print(f"\nУникальных систем: {len(results['project_summary']['all_systems'])}")
        
        if results['project_summary']['all_standards']:
            print(f"Уникальных стандартов: {len(results['project_summary']['all_standards'])}")
        
        if results['cross_references']:
            print(f"\nПерекрестных ссылок между файлами: {len(results['cross_references'])}")


def main():
    """Основная функция для запуска анализатора"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Универсальный анализатор проектной документации с отдельными отчётами',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s ./pdf_folder
  %(prog)s ./pdf_folder -c config/custom_config.json
  %(prog)s ./pdf_folder -o results/project_analysis.json -v
        """
    )
    parser.add_argument('input_folder', help='Папка с PDF файлами для анализа')
    parser.add_argument('-c', '--config', default='config/analyzer_config.json', 
                       help='Путь к конфигурационному файлу')
    parser.add_argument('-o', '--output', help='Выходной JSON файл для сводного отчёта')
    parser.add_argument('-v', '--verbose', action='store_true', help='Подробный вывод')
    parser.add_argument('--no-individual', action='store_true', 
                       help='Не создавать отдельные отчёты для каждого файла')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_folder):
        print(f"Ошибка: Папка '{args.input_folder}' не существует")
        sys.exit(1)
    
    if args.verbose:
        print(f"Конфигурационный файл: {args.config}")
        print(f"Входная папка: {args.input_folder}")
        print(f"Создание отдельных отчётов: {'нет' if args.no_individual else 'да'}")
    
    try:
        analyzer = ConfigurableGPTAnalyzer(args.config)
        
        if args.no_individual:
            analyzer.save_individual_reports = False
        
        results = analyzer.analyze_pdf_files(args.input_folder, args.output)
        
        print(f"\n✓ Анализ успешно завершен!")
        
        if analyzer.save_individual_reports:
            print(f"✓ Отдельные отчёты сохранены в: {analyzer.reports_output_dir}")
        
    except Exception as e:
        print(f"\n✗ Ошибка анализа: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()