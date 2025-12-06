# [file name]: main.py
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

# Импорты процессоров
from base_processor import BaseDocumentProcessor, DocumentPostProcessor
from pdf_processor import PDFProcessor
from docx_processor import DOCXProcessor
from xlsx_processor import XLSXProcessor
from txt_processor import TXTProcessor


class DocumentConverter:
    """Основной класс для конвертации документов"""

    def __init__(self, config_path: str = "config.json"):
        # Инициализируем logger сразу
        self.logger = logging.getLogger(__name__)
        
        self.config = self._load_config(config_path)
        self.setup_logging()
        
        # Создание рабочих директорий
        self._setup_working_directories()
        
        # Инициализация процессоров
        self.processors: List[BaseDocumentProcessor] = [
            PDFProcessor(self.config),
            DOCXProcessor(self.config),
            XLSXProcessor(self.config),
            TXTProcessor(self.config)
        ]
        
        self.post_processor = DocumentPostProcessor(self.config)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Загрузка конфигурации"""
        default_config = {
            "input_settings": {
                "default_input_directory": "documents",
                "supported_formats": [".pdf", ".docx", ".xlsx", ".txt", ".md", ".xls"]
            },
            "output_settings": {
                "default_output_directory": "converted_documents",
                "base_output_directory": "output",
                "converted_txt_dir": "txt_files",
                "log_level": "INFO"
            },
            "processing_settings": {
                "max_file_size": 100 * 1024 * 1024,
                "cleanup_temp_files": True,
                "encoding": "utf-8"
            }
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                # Рекурсивное обновление конфигурации
                self._update_config_dict(default_config, user_config)
                print(f"✅ Конфигурация загружена из {config_path}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки конфигурации: {e}, используются настройки по умолчанию")
        else:
            print("ℹ️ Файл конфигурации не найден, используются настройки по умолчанию")
            # Создаем файл конфигурации по умолчанию
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                print(f"✅ Создан файл конфигурации по умолчанию: {config_path}")
            except Exception as e:
                print(f"⚠️ Не удалось создать файл конфигурации: {e}")
        
        return default_config

    def _update_config_dict(self, default: Dict, user: Dict):
        """Рекурсивное обновление конфигурации"""
        for key, value in user.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self._update_config_dict(default[key], value)
            else:
                default[key] = value

    def _setup_working_directories(self):
        """Создание рабочих директорий"""
        # Создаем папку для исходных документов
        input_dir = self.config["input_settings"]["default_input_directory"]
        if not os.path.exists(input_dir):
            os.makedirs(input_dir, exist_ok=True)
            print(f"✅ Создана папка для исходных документов: {input_dir}")
        
        # Создаем выходные директории
        output_settings = self.config["output_settings"]
        base_dir = output_settings["base_output_directory"]
        converted_dir = output_settings["converted_txt_dir"]
        
        self.output_dir = os.path.join(base_dir, converted_dir)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            print(f"✅ Создана папка для конвертированных файлов: {self.output_dir}")

    def setup_logging(self):
        """Настройка логирования"""
        log_level = self.config["output_settings"].get("log_level", "INFO")
        log_level = getattr(logging, log_level.upper())
        
        # Настраиваем logging только если еще не настроен
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.StreamHandler(),
                    logging.FileHandler('document_converter.log', encoding='utf-8')
                ]
            )
        
        self.logger.info("Логирование инициализировано")

    def get_processor(self, file_path: str) -> Optional[BaseDocumentProcessor]:
        """Получение подходящего процессора для файла"""
        for processor in self.processors:
            if processor.can_process(file_path):
                return processor
        return None

    def ensure_documents_directory(self) -> bool:
        """Проверяет наличие папки documents и создает её если нужно"""
        input_dir = self.config["input_settings"]["default_input_directory"]
        if not os.path.exists(input_dir):
            os.makedirs(input_dir, exist_ok=True)
            self.logger.info(f"Создана папка '{input_dir}'. Поместите туда файлы для конвертации.")
            return False
        return True

    def get_documents_count(self) -> int:
        """Возвращает количество документов в папке"""
        input_dir = self.config["input_settings"]["default_input_directory"]
        supported_formats = self.config["input_settings"]["supported_formats"]
        
        if not os.path.exists(input_dir):
            return 0
        
        count = 0
        for file_path in Path(input_dir).iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                count += 1
        
        return count

    def list_documents(self):
        """Показывает список документов в папке"""
        input_dir = self.config["input_settings"]["default_input_directory"]
        supported_formats = self.config["input_settings"]["supported_formats"]
        
        if not self.ensure_documents_directory():
            print(f"📁 Папка '{input_dir}' создана. Добавьте файлы для конвертации.")
            return
        
        print(f"📂 Документы в папке '{input_dir}':")
        print("-" * 50)
        
        found_files = False
        for file_path in sorted(Path(input_dir).iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                file_size = file_path.stat().st_size
                size_kb = file_size / 1024
                print(f"  📄 {file_path.name} ({size_kb:.1f} KB)")
                found_files = True
        
        if not found_files:
            print("  ❌ Поддерживаемые файлы не найдены")
            supported_fmts = ", ".join(self.config["input_settings"]["supported_formats"])
            print(f"  💡 Поддерживаемые форматы: {supported_fmts}")

    def process_single_file(self, file_path: str) -> Dict[str, Any]:
        """Обработка одного файла"""
        try:
            self.logger.info(f"Начало обработки файла: {file_path}")
            
            # Проверка существования файла
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Файл не найден: {file_path}")

            # Проверка размера файла
            max_size = self.config["processing_settings"]["max_file_size"]
            file_size = os.path.getsize(file_path)
            if file_size > max_size:
                raise ValueError(f"Файл слишком большой: {file_size} байт (максимум: {max_size} байт)")

            # Получение подходящего процессора
            processor = self.get_processor(file_path)
            if not processor:
                raise ValueError(f"Неподдерживаемый формат файла: {file_path}")

            # Конвертация в TXT
            temp_output = processor.convert_to_txt(file_path, self.output_dir)
            
            # Чтение конвертированного содержимого
            with open(temp_output, 'r', encoding='utf-8') as f:
                content = f.read()

            # Пост-обработка содержимого
            title, metadata = self.post_processor.extract_metadata_and_title(content, file_path)
            
            # Улучшение структуры содержимого
            enhanced_content = self.post_processor.enhance_content_structure(content)
            enhanced_content = self.post_processor.process_title_section(enhanced_content)
            enhanced_content = self.post_processor.process_preface_section(enhanced_content)
            
            # Добавление метаданных
            final_content = self.post_processor.add_metadata_section(
                enhanced_content, title, metadata
            )

            # Перезаписываем файл с улучшенной структурой
            with open(temp_output, 'w', encoding='utf-8') as f:
                f.write(final_content)

            result = {
                "status": "success",
                "input_file": file_path,
                "output_file": temp_output,
                "title": title,
                "metadata": metadata,
                "file_size": file_size,
                "content_length": len(final_content)
            }

            self.logger.info(f"Файл успешно обработан: {file_path} -> {temp_output}")
            return result

        except Exception as e:
            self.logger.error(f"Ошибка обработки файла {file_path}: {e}")
            return {
                "status": "error",
                "input_file": file_path,
                "error": str(e)
            }

    def process_directory(self, input_dir: str) -> List[Dict[str, Any]]:
        """Обработка всех файлов в директории"""
        self.logger.info(f"Начало обработки директории: {input_dir}")
        
        if not os.path.isdir(input_dir):
            raise ValueError(f"Директория не существует: {input_dir}")

        results = []
        supported_formats = self.config["input_settings"]["supported_formats"]
        
        # Обработка файлов в директории
        for file_path in Path(input_dir).iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                result = self.process_single_file(str(file_path))
                results.append(result)
        
        # Статистика обработки
        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] == "error")
        
        self.logger.info(f"Обработка завершена. Успешно: {success_count}, Ошибок: {error_count}")
        return results

    def process_default_directory(self) -> List[Dict[str, Any]]:
        """Обработка документов из папки по умолчанию"""
        input_dir = self.config["input_settings"]["default_input_directory"]
        
        # Проверяем наличие папки documents
        if not self.ensure_documents_directory():
            return []
        
        documents_count = self.get_documents_count()
        
        if documents_count == 0:
            self.logger.warning(f"В папке '{input_dir}' не найдено поддерживаемых файлов")
            return []
        
        self.logger.info(f"Найдено документов для конвертации: {documents_count}")
        return self.process_directory(input_dir)

    def save_conversion_report(self, results: List[Dict[str, Any]]):
        """Сохраняет отчет о конвертации"""
        report_path = os.path.join(self.output_dir, "conversion_report.txt")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("ОТЧЕТ О КОНВЕРТАЦИИ ДОКУМЕНТОВ\n")
            f.write("=" * 50 + "\n\n")
            
            success_count = sum(1 for r in results if r["status"] == "success")
            error_count = sum(1 for r in results if r["status"] == "error")
            
            f.write(f"Всего файлов: {len(results)}\n")
            f.write(f"Успешно: {success_count}\n")
            f.write(f"С ошибками: {error_count}\n\n")
            
            for i, result in enumerate(results, 1):
                f.write(f"ДОКУМЕНТ {i}:\n")
                f.write(f"  📄 Входной файл: {Path(result['input_file']).name}\n")
                
                if result['status'] == 'success':
                    f.write(f"  ✅ Конвертированный: {Path(result['output_file']).name}\n")
                    if 'title' in result:
                        f.write(f"  📝 Заголовок: {result['title']}\n")
                else:
                    f.write(f"  ❌ Ошибка: {result['error']}\n")
                f.write("-" * 40 + "\n")
        
        self.logger.info(f"Отчет сохранен: {report_path}")
        return report_path

    def show_output_structure(self):
        """Показывает структуру выходных папок"""
        output_dir = Path(self.config["output_settings"]["base_output_directory"])
        
        if not output_dir.exists():
            print("📁 Выходная структура еще не создана.")
            print("   Запустите конвертацию для создания папок.")
            return
        
        print("📁 Структура выходных папок:")
        print("-" * 40)
        
        def print_tree(directory, prefix=""):
            items = list(directory.iterdir())
            if not items:
                print(f"{prefix}📁 (пусто)")
                return
                
            for item in sorted(items):
                if item.is_dir():
                    print(f"{prefix}📁 {item.name}/")
                    print_tree(item, prefix + "  ")
                else:
                    file_size = item.stat().st_size
                    size_kb = file_size / 1024
                    print(f"{prefix}📄 {item.name} ({size_kb:.1f} KB)")
        
        print_tree(output_dir)


def main():
    """Основная функция для запуска из командной строки"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Конвертер документов в TXT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                         # Конвертация из папки documents
  python main.py --list                  # Показать список документов
  python main.py --structure             # Показать структуру выходных папок
  python main.py --input file.pdf        # Обработать конкретный файл
  python main.py --input /path/to/docs   # Обработать папку
  python main.py --config my_config.json # Использовать свой конфиг
        """
    )
    
    parser.add_argument('--config', default='config.json', 
                       help='Путь к конфигурационному файлу (по умолчанию: config.json)')
    parser.add_argument('--input', 
                       help='Путь к файлу или директории для обработки')
    parser.add_argument('--list', '--list-docs', action='store_true', 
                       help='Показать список документов в папке по умолчанию')
    parser.add_argument('--structure', '--show-structure', action='store_true', 
                       help='Показать структуру выходных папок')
    
    args = parser.parse_args()
    
    print("🔄 Конвертер документов в текстовый формат")
    print("=" * 50)
    
    try:
        # Создаем конвертер
        converter = DocumentConverter(args.config)
        
        if args.list:
            converter.list_documents()
        elif args.structure:
            converter.show_output_structure()
        elif args.input:
            # Обработка указанного файла или директории
            if os.path.isfile(args.input):
                results = [converter.process_single_file(args.input)]
            elif os.path.isdir(args.input):
                results = converter.process_directory(args.input)
            else:
                print(f"❌ Ошибка: путь не существует - {args.input}")
                return
            
            # Сохраняем отчет
            converter.save_conversion_report(results)
            
            # Вывод статистики
            success_count = sum(1 for r in results if r["status"] == "success")
            error_count = sum(1 for r in results if r["status"] == "error")
            
            print(f"✅ Обработка завершена: {success_count} успешно, {error_count} с ошибками")
            
        else:
            # Обработка папки documents по умолчанию
            print("🔍 Поиск документов в папке 'documents'...")
            
            documents_count = converter.get_documents_count()
            if documents_count == 0:
                print("❌ В папке 'documents' не найдено поддерживаемых файлов.")
                supported_fmts = ", ".join(converter.config["input_settings"]["supported_formats"])
                print(f"💡 Поддерживаемые форматы: {supported_fmts}")
                print("💡 Используйте --list для просмотра файлов")
                return
            
            print(f"📄 Найдено документов для конвертации: {documents_count}")
            print("🔄 Запуск конвертации...")
            
            results = converter.process_default_directory()
            report_path = converter.save_conversion_report(results)
            
            success_count = sum(1 for r in results if r["status"] == "success")
            error_count = sum(1 for r in results if r["status"] == "error")
            
            print(f"✅ Конвертация завершена!")
            print(f"📊 Результат: {success_count} успешно, {error_count} с ошибками")
            print(f"📁 Результаты в: {converter.output_dir}")
            print(f"📋 Отчет: {report_path}")
            
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()