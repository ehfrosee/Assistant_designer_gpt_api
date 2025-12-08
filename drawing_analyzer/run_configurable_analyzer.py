#!/usr/bin/env python3
"""
Запуск конфигурируемого анализатора проектной документации
"""

import os
import sys
import glob
from configurable_gpt_analyzer import ConfigurableGPTAnalyzer

def main():
    # Конфигурация
    config_file = "config/analyzer_config.json"
    input_folder = "data/input"
    output_file = "data/output/project_analysis.json"
    
    # Проверяем наличие папки с документами
    if not os.path.exists(input_folder):
        print(f"\nСоздаю структуру папок...")
        os.makedirs(input_folder, exist_ok=True)
        os.makedirs("data/output/individual_reports", exist_ok=True)
        os.makedirs("config", exist_ok=True)
        
        print(f"\n✓ Структура папок создана:")
        print(f"  {os.path.abspath(input_folder)} - поместите сюда PDF файлы")
        print(f"  data/output/individual_reports - здесь будут отчёты по файлам")
        print(f"  config - здесь находится конфигурация")
        
        print(f"\nПоместите PDF файлы в папку '{input_folder}'")
        print(f"и запустите программу снова.")
        return
    
    # Проверяем наличие файлов с улучшенным поиском
    pdf_files = []
    seen_files = set()
    
    # Ищем все PDF файлы
    for pattern in ["*.pdf", "*.PDF"]:
        for file_path in glob.glob(os.path.join(input_folder, pattern)):
            try:
                file_name = os.path.basename(file_path)
                # Нормализуем для сравнения
                normalized = file_name.lower()
                if normalized not in seen_files:
                    seen_files.add(normalized)
                    pdf_files.append(file_path)
            except Exception as e:
                print(f"Ошибка обработки файла {file_path}: {e}")
                continue
    
    if not pdf_files:
        print(f"\n✗ Ошибка: Не найдены PDF файлы в папке '{input_folder}'")
        print(f"Поместите PDF файлы в папку и запустите программу снова.")
        return
    
    print(f"\n✓ Найдено уникальных PDF файлов: {len(pdf_files)}")
    
    # Показываем список файлов
    for i, file_path in enumerate(sorted(pdf_files), 1):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) / 1024  # в КБ
        print(f"  {i:2d}. {file_name} ({file_size:.1f} КБ)")
    
    # Инициализация анализатора
    try:
        analyzer = ConfigurableGPTAnalyzer(config_file)
        
        print(f"\n" + "="*60)
        print(f"НАЧАЛО АНАЛИЗА")
        print(f"Папка: {input_folder}")
        print("="*60)
        
        # Запуск анализа
        results = analyzer.analyze_pdf_files(input_folder, output_file)
        
        print(f"\n" + "="*60)
        print("АНАЛИЗ ЗАВЕРШЕН УСПЕШНО")
        print("="*60)
        
        # Вывод результатов
        print(f"\n✓ Сводный отчёт: {output_file}")
        print(f"✓ Уникальных файлов проанализировано: {results['total_files']}")
        print(f"✓ Всего страниц: {results['project_summary']['total_pages']}")
        
        if analyzer.save_individual_reports and results.get('individual_reports'):
            print(f"\n✓ Отдельные отчёты созданы:")
            for report in results['individual_reports']:
                print(f"  • {report['file_name']}")
        
        if 'cross_references' in results and results['cross_references']:
            print(f"✓ Найдено перекрестных ссылок: {len(results['cross_references'])}")
        
        # Показываем путь к файлам
        abs_summary = os.path.abspath(output_file)
        print(f"\n📍 Абсолютный путь к сводному отчёту: {abs_summary}")
        
        if analyzer.save_individual_reports:
            abs_reports_dir = os.path.abspath(analyzer.reports_output_dir)
            print(f"📍 Папка с отчётами по файлам: {abs_reports_dir}")
        
        print(f"\n📊 Статистика по типам файлов:")
        file_types = {}
        for file_info in results['files']:
            file_type = file_info['file_type']
            file_types[file_type] = file_types.get(file_type, 0) + 1
        
        for file_type, count in file_types.items():
            print(f"  • {file_type}: {count} файл(ов)")
        
    except Exception as e:
        print(f"\n✗ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()