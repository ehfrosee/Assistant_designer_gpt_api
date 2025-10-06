# -*- coding: utf-8 -*-
"""Скрипт для тестирования ассистента"""

import os
import json
import csv
import requests
import logging
from typing import List, Dict
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация API
API_BASE_URL = os.getenv('API_BASE_URL', 'http://127.0.0.1:5000')

class AssistantTester:
    """Класс для тестирования ассистента"""
    
    def __init__(self, questions_file: str = "test_questions.txt", output_file: str = "test_report.txt"):
        self.questions_file = questions_file
        self.output_file = output_file
        self.questions = []
        self.results = []
    
    def load_questions(self) -> bool:
        """Загрузка вопросов из файла"""
        try:
            with open(self.questions_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Фильтруем пустые строки и строки с комментариями
            self.questions = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.questions.append(line)
            
            logger.info(f"Загружено {len(self.questions)} вопросов из файла {self.questions_file}")
            return True
            
        except FileNotFoundError:
            logger.error(f"Файл с вопросами {self.questions_file} не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки вопросов: {e}")
            return False
    
    def test_question(self, question: str, question_num: int) -> Dict:
        """Тестирование одного вопроса"""
        try:
            logger.info(f"Тестируем вопрос {question_num}: {question[:50]}...")
            
            # Отправляем запрос к API
            response = requests.post(
                f"{API_BASE_URL}/api/ask",
                json={"question": question, "temperature": 0.0},
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'question_num': question_num,
                    'question': question,
                    'answer': data.get('answer', ''),
                    'tokens_used': data.get('tokens_used', 0),
                    'sources_count': len(data.get('sources', [])),
                    'success': True,
                    'error': None
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"Ошибка API для вопроса {question_num}: {error_msg}")
                return {
                    'question_num': question_num,
                    'question': question,
                    'answer': '',
                    'tokens_used': 0,
                    'sources_count': 0,
                    'success': False,
                    'error': error_msg
                }
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка соединения: {e}"
            logger.error(f"Ошибка соединения для вопроса {question_num}: {e}")
            return {
                'question_num': question_num,
                'question': question,
                'answer': '',
                'tokens_used': 0,
                'sources_count': 0,
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Неожиданная ошибка: {e}"
            logger.error(f"Неожиданная ошибка для вопроса {question_num}: {e}")
            return {
                'question_num': question_num,
                'question': question,
                'answer': '',
                'tokens_used': 0,
                'sources_count': 0,
                'success': False,
                'error': error_msg
            }
    
    def run_tests(self) -> bool:
        """Запуск всех тестов"""
        if not self.load_questions():
            return False
        
        if not self.questions:
            logger.error("Нет вопросов для тестирования")
            return False
        
        logger.info(f"Начинаем тестирование {len(self.questions)} вопросов...")
        
        self.results = []
        successful_tests = 0
        
        for i, question in enumerate(self.questions, 1):
            result = self.test_question(question, i)
            self.results.append(result)
            
            if result['success']:
                successful_tests += 1
                logger.info(f"✅ Вопрос {i} обработан успешно. Токенов: {result['tokens_used']}")
            else:
                logger.error(f"❌ Вопрос {i} завершился с ошибкой: {result['error']}")
            
            # Небольшая пауза между запросами чтобы не перегружать API
            import time
            time.sleep(1)
        
        logger.info(f"Тестирование завершено. Успешно: {successful_tests}/{len(self.questions)}")
        return successful_tests > 0
    
    def generate_report(self) -> bool:
        """Генерация отчета в текстовом формате"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                # Заголовок отчета
                f.write(f"Отчет тестирования ассистента\n")
                f.write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
                f.write(f"Всего вопросов: {len(self.results)}\n")
                f.write(f"Успешных ответов: {sum(1 for r in self.results if r['success'])}\n")
                f.write(f"API: {API_BASE_URL}\n")
                f.write("=" * 80 + "\n\n")
                
                # Результаты по каждому вопросу
                for result in self.results:
                    f.write(f"Вопрос № {result['question_num']}. {result['question']}\n")
                    
                    if result['success']:
                        f.write(f"Ответ: {result['answer']}\n")
                        f.write(f"[Токенов использовано: {result['tokens_used']}, Источников: {result['sources_count']}]\n")
                    else:
                        f.write(f"Ответ: ОШИБКА - {result['error']}\n")
                    
                    f.write("\n")  # Пустая строка-разделитель
            
            logger.info(f"Отчет сохранен в файл: {self.output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения отчета: {e}")
            return False
    
    def generate_csv_report(self) -> bool:
        """Генерация отчета в CSV формате"""
        try:
            csv_file = self.output_file.replace('.txt', '.csv')
            
            with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                
                # Заголовок CSV
                writer.writerow(['Номер вопроса', 'Вопрос', 'Ответ'])
                
                # Данные
                for result in self.results:
                    question_num = result['question_num']
                    question = result['question']
                    
                    if result['success']:
                        answer = result['answer']
                    else:
                        answer = f"ОШИБКА: {result['error']}"
                    
                    writer.writerow([question_num, question, answer])
            
            logger.info(f"CSV отчет сохранен в файл: {csv_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения CSV отчета: {e}")
            return False
    
    def generate_detailed_report(self) -> bool:
        """Генерация детального отчета в JSON формате"""
        try:
            report_data = {
                'timestamp': datetime.now().isoformat(),
                'api_url': API_BASE_URL,
                'total_questions': len(self.results),
                'successful_answers': sum(1 for r in self.results if r['success']),
                'total_tokens_used': sum(r['tokens_used'] for r in self.results if r['success']),
                'results': self.results
            }
            
            json_file = self.output_file.replace('.txt', '_detailed.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Детальный отчет сохранен в файл: {json_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения детального отчета: {e}")
            return False
    
    def print_summary(self):
        """Вывод сводки тестирования в консоль"""
        successful = sum(1 for r in self.results if r['success'])
        total_tokens = sum(r['tokens_used'] for r in self.results if r['success'])
        avg_tokens = total_tokens / successful if successful > 0 else 0
        
        print("\n" + "=" * 60)
        print("СВОДКА ТЕСТИРОВАНИЯ")
        print("=" * 60)
        print(f"Всего вопросов: {len(self.results)}")
        print(f"Успешных ответов: {successful}")
        print(f"Ошибок: {len(self.results) - successful}")
        print(f"Общее количество токенов: {total_tokens}")
        print(f"Среднее токенов на ответ: {avg_tokens:.1f}")
        print(f"Текстовый отчет: {self.output_file}")
        print(f"CSV отчет: {self.output_file.replace('.txt', '.csv')}")
        
        # Статистика по источникам
        if successful > 0:
            sources_stats = {}
            for result in self.results:
                if result['success']:
                    count = result['sources_count']
                    sources_stats[count] = sources_stats.get(count, 0) + 1
            
            print("\nСтатистика по источникам:")
            for count, freq in sorted(sources_stats.items()):
                print(f"  {count} источников: {freq} вопросов")

def main():
    """Основная функция тестирования"""
    print("Тестирование ассистента")
    print("=" * 40)
    
    # Проверяем доступность API
    try:
        response = requests.get(f"{API_BASE_URL}/api/health", timeout=10)
        if response.status_code != 200:
            print(f"❌ API недоступен: {response.status_code}")
            return
        health_data = response.json()
        print(f"✅ API доступен. Статус: {health_data.get('status', 'unknown')}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Не удалось подключиться к API: {e}")
        return
    
    # Получаем информацию о базе знаний
    try:
        response = requests.get(f"{API_BASE_URL}/api/knowledge-base/info", timeout=10)
        if response.status_code == 200:
            kb_info = response.json()
            print(f"📚 База знаний: {kb_info.get('name', 'Unknown')}")
            print(f"   Документов: {kb_info.get('documents_count', 0)}")
            print(f"   Статус: {kb_info.get('status', 'unknown')}")
    except Exception as e:
        print(f"⚠️ Не удалось получить информацию о базе знаний: {e}")
    
    # Запускаем тестирование
    tester = AssistantTester()
    
    if tester.run_tests():
        # Генерируем отчеты
        tester.generate_report()
        tester.generate_csv_report()
        tester.generate_detailed_report()
        tester.print_summary()
    else:
        print("❌ Тестирование завершилось с ошибками")

if __name__ == '__main__':
    main()