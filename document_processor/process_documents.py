# [file name]: process_documents.py
#!/usr/bin/env python3
"""
Скрипт для запуска конвертации документов из папки 'documents'
"""

import os
import sys
import argparse
from pathlib import Path

# Добавляем текущую директорию в путь для импорта модулей
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

from document_converter import DocumentConverter


def ensure_documents_directory():
    """Проверяет наличие папки documents и создает её если нужно"""
    documents_dir = current_dir / "documents"
    if not documents_dir.exists():
        documents_dir.mkdir(exist_ok=True)
        print(f"📁 Создана папка 'documents'. Поместите туда файлы для конвертации.")
        return False
    return True


def get_documents_count():
    """Возвращает количество документов в папке"""
    documents_dir = current_dir / "documents"
    supported_formats = ['.pdf', '.docx', '.txt', '.md', '.xlsx', '.xls']
    
    count = 0
    for file_path in documents_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in supported_formats:
            count += 1
    
    return count


def process_documents(config_path="config.json"):
    """
    Основная функция конвертации документов из папки 'documents'
    """
    
    # Проверяем наличие папки documents
    if not ensure_documents_directory():
        return
    
    documents_dir = current_dir / "documents"
    documents_count = get_documents_count()
    
    if documents_count == 0:
        print("❌ В папке 'documents' не найдено поддерживаемых файлов.")
        print("💡 Поддерживаемые форматы: .pdf, .docx, .txt, .md, .xlsx, .xls")
        return
    
    print(f"📄 Найдено документов для конвертации: {documents_count}")
    print("=" * 50)
    
    # Конвертация документов
    print("🔄 Запуск конвертации документов...")
    converter = DocumentConverter(config_path)
    
    conversion_results = converter.process_directory(str(documents_dir))
    
    print(f"✅ Конвертация завершена!")
    print(f"📊 Сконвертировано файлов: {len(conversion_results)}")
    print(f"📁 Результаты в: converted_documents/txt_files/")
    
    # Сохраняем отчет
    save_conversion_report(conversion_results)


def save_conversion_report(results):
    """Сохраняет отчет о конвертации"""
    report_path = current_dir / "converted_documents" / "conversion_report.txt"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("ОТЧЕТ О КОНВЕРТАЦИИ ДОКУМЕНТОВ\n")
        f.write("=" * 50 + "\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"ДОКУМЕНТ {i}:\n")
            f.write(f"  📄 Входной файл: {Path(result['input_path']).name}\n")
            f.write(f"  📝 Конвертированный: {Path(result['converted_txt']).name}\n")
            f.write("-" * 30 + "\n")
    
    print(f"📋 Отчет сохранен: {report_path}")


def list_documents():
    """Показывает список документов в папке"""
    if not ensure_documents_directory():
        return
    
    documents_dir = current_dir / "documents"
    supported_formats = ['.pdf', '.docx', '.txt', '.md', '.xlsx', '.xls']
    
    print("📂 Документы в папке 'documents':")
    print("-" * 40)
    
    found_files = False
    for file_path in sorted(documents_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in supported_formats:
            file_size = file_path.stat().st_size
            size_kb = file_size / 1024
            print(f"  📄 {file_path.name} ({size_kb:.1f} KB)")
            found_files = True
    
    if not found_files:
        print("  ❌ Поддерживаемые файлы не найдены")
        print("  💡 Поддерживаемые форматы: .pdf, .docx, .txt, .md, .xlsx, .xls")


def show_output_structure():
    """Показывает структуру выходных папок"""
    output_dir = current_dir / "converted_documents"
    
    if not output_dir.exists():
        print("📁 Выходная структура еще не создана.")
        print("   Запустите конвертацию для создания папок.")
        return
    
    print("📁 Структура выходных папок:")
    print("-" * 40)
    
    def print_tree(directory, prefix=""):
        for item in sorted(directory.iterdir()):
            if item.is_dir():
                print(f"{prefix}📁 {item.name}/")
                print_tree(item, prefix + "  ")
            else:
                file_size = item.stat().st_size
                size_kb = file_size / 1024
                print(f"{prefix}📄 {item.name} ({size_kb:.1f} KB)")
    
    print_tree(output_dir)


def main():
    """Основная функция CLI"""
    parser = argparse.ArgumentParser(
        description='Конвертация документов из папки "documents" в текстовый формат',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python process_documents.py              # Конвертация всех документов
  python process_documents.py --list       # Показать список документов
  python process_documents.py --structure  # Показать структуру выходных папок
        """
    )
    
    parser.add_argument('--config', default='config.json', 
                       help='Путь к конфигурационному файлу (по умолчанию: config.json)')
    parser.add_argument('--list', '--list-docs', action='store_true', 
                       help='Показать список документов в папке')
    parser.add_argument('--structure', '--show-structure', action='store_true', 
                       help='Показать структуру выходных папок')
    
    args = parser.parse_args()
    
    print("🔄 Конвертер документов в текстовый формат")
    print("=" * 40)
    
    if args.list:
        list_documents()
    elif args.structure:
        show_output_structure()
    else:
        process_documents(config_path=args.config)


if __name__ == "__main__":
    main()