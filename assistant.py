# -*- coding: utf-8 -*-
"""Класс Assistant для работы с ChatGPT и обработки документов"""

import os
import re
import json
import openai
import tiktoken
import numpy as np
import faiss
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
import requests
from pathlib import Path
import pickle
from datetime import datetime


class DocumentProcessor:
    """Класс для обработки документов"""

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def read_text_file(self, file_path: str) -> str:
        """Чтение текстового файла с разными кодировками"""
        encodings = ['utf-8', 'cp1251', 'latin1']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Не удалось прочитать файл {file_path}")

    def read_pdf_file(self, file_path: str) -> str:
        """Чтение PDF файла"""
        try:
            from pdfminer.high_level import extract_text
            return extract_text(file_path)
        except ImportError:
            # Простой fallback для текста из PDF
            import subprocess
            try:
                result = subprocess.run(['pdftotext', file_path, '-'],
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout
            except:
                pass
            return f"Содержимое PDF файла {os.path.basename(file_path)}"

    def text_to_markdown(self, text: str) -> str:
        """
        Преобразование текста в markdown формат с дублированием заголовков.
        Это помогает сохранить структурную информацию в содержимом чанков.
        """
        if not text.strip():
            return text

        # Обрабатываем заголовки разных уровней
        def replace_header1(match):
            return f"## {match.group(1)}\n{match.group(1)}"

        text = re.sub(r'^## (.+)', replace_header1, text, flags=re.M)

        def replace_header2(match):
            return f"### {match.group(1)}\n{match.group(1)}"

        text = re.sub(r'^### (.+)', replace_header2, text, flags=re.M)

        def replace_header3(match):
            return f"#### {match.group(1)}\n{match.group(1)}"

        text = re.sub(r'^#### (.+)', replace_header3, text, flags=re.M)

        return text

    def split_text_by_markdown_headers(self, text: str, filename: str, use_markdown: bool = False) -> List[
        Dict[str, Any]]:
        """
        Разделение текста на чанки по markdown заголовкам.
        """
        if not text.strip():
            return []

        # Применяем markdown преобразование если нужно
        if use_markdown:
            text = self.text_to_markdown(text)

        # Регулярные выражения для поиска заголовков
        header_patterns = [
            (r'^# (.+)$', 'h1'),  # Заголовок уровня 1
            (r'^## (.+)$', 'h2'),  # Заголовок уровня 2
            (r'^### (.+)$', 'h3'),  # Заголовок уровня 3
            (r'^#### (.+)$', 'h4'),  # Заголовок уровня 4
        ]

        # Разделяем текст по строкам
        lines = text.split('\n')
        chunks = []
        current_chunk = []
        current_header = "Документ"
        document_title = filename  # По умолчанию используем имя файла как название документа
        header_stack = [current_header]

        for line in lines:
            line = line.strip()
            if not line:
                if current_chunk:
                    current_chunk.append('')
                continue

            # Проверяем, является ли строка заголовком
            is_header = False
            header_level = None
            header_text = None

            for pattern, level in header_patterns:
                match = re.match(pattern, line)
                if match:
                    is_header = True
                    header_level = level
                    header_text = match.group(1).strip()
                    break

            if is_header:
                # Сохраняем текущий чанк если он не пустой
                if current_chunk:
                    chunk_content = '\n'.join(current_chunk).strip()
                    if chunk_content:
                        chunks.append({
                            'content': chunk_content,
                            'metadata': {
                                'source': filename,
                                'header': current_header,
                                'header_path': ' -> '.join(header_stack),
                                'document_title': document_title  # Сохраняем название документа
                            },
                            'tokens': self.count_tokens(chunk_content)
                        })

                # Обновляем текущий заголовок и стек
                current_header = header_text

                # Если это заголовок уровня 1, сохраняем как название документа
                if header_level == 'h1':
                    document_title = header_text  # Сохраняем название документа
                    header_stack = [header_text]
                elif header_level == 'h2':
                    header_stack = header_stack[:1] + [header_text]
                elif header_level == 'h3':
                    header_stack = header_stack[:2] + [header_text]
                elif header_level == 'h4':
                    header_stack = header_stack[:3] + [header_text]

                # Начинаем новый чанк
                current_chunk = [line]

            else:
                # Добавляем строку к текущему чанку
                current_chunk.append(line)

                # Проверяем размер чанка
                current_content = '\n'.join(current_chunk)
                if self.count_tokens(current_content) > self.chunk_size:
                    # Если чанк слишком большой, разбиваем его
                    if len(current_chunk) > 1:
                        # Сохраняем первую часть
                        first_part = current_chunk[:-1]
                        chunk_content = '\n'.join(first_part).strip()
                        if chunk_content:
                            chunks.append({
                                'content': chunk_content,
                                'metadata': {
                                    'source': filename,
                                    'header': current_header,
                                    'header_path': ' -> '.join(header_stack),
                                    'document_title': document_title  # Сохраняем название документа
                                },
                                'tokens': self.count_tokens(chunk_content)
                            })

                        # Начинаем новый чанк с последней строки
                        current_chunk = [current_chunk[-1]]
                    else:
                        # Если одна строка слишком большая, принудительно разбиваем
                        words = current_chunk[0].split()
                        half_point = len(words) // 2
                        first_half = ' '.join(words[:half_point])
                        second_half = ' '.join(words[half_point:])

                        chunk_content = first_half.strip()
                        if chunk_content:
                            chunks.append({
                                'content': chunk_content,
                                'metadata': {
                                    'source': filename,
                                    'header': current_header,
                                    'header_path': ' -> '.join(header_stack),
                                    'document_title': document_title  # Сохраняем название документа
                                },
                                'tokens': self.count_tokens(chunk_content)
                            })

                        current_chunk = [second_half]

        # Добавляем последний чанк
        if current_chunk:
            chunk_content = '\n'.join(current_chunk).strip()
            if chunk_content:
                chunks.append({
                    'content': chunk_content,
                    'metadata': {
                        'source': filename,
                        'header': current_header,
                        'header_path': ' -> '.join(header_stack),
                        'document_title': document_title  # Сохраняем название документа
                    },
                    'tokens': self.count_tokens(chunk_content)
                })

        return chunks

    def split_text(self, text: str, filename: str, use_markdown: bool = False) -> List[Dict[str, Any]]:
        """
        Основной метод разделения текста на чанки.
        """
        # Если включена markdown обработка, используем специализированный метод
        if use_markdown:
            return self.split_text_by_markdown_headers(text, filename, use_markdown)

        # Стандартное разделение (оригинальная логика) с добавлением document_title
        if not text.strip():
            return []

        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            if len(current_chunk) + len(paragraph) + 1 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    chunks.append({
                        'content': current_chunk,
                        'metadata': {
                            'source': filename,
                            'document_title': filename  # Используем имя файла как название документа
                        },
                        'tokens': self.count_tokens(current_chunk)
                    })

                if len(paragraph) > self.chunk_size:
                    sentences = re.split(r'[.!?]+', paragraph)
                    current_chunk = ""
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        if len(current_chunk) + len(sentence) + 1 <= self.chunk_size:
                            if current_chunk:
                                current_chunk += " " + sentence
                            else:
                                current_chunk = sentence
                        else:
                            if current_chunk:
                                chunks.append({
                                    'content': current_chunk,
                                    'metadata': {
                                        'source': filename,
                                        'document_title': filename  # Используем имя файла как название документа
                                    },
                                    'tokens': self.count_tokens(current_chunk)
                                })
                            current_chunk = sentence
                else:
                    current_chunk = paragraph

        if current_chunk:
            chunks.append({
                'content': current_chunk,
                'metadata': {
                    'source': filename,
                    'document_title': filename  # Используем имя файла как название документа
                },
                'tokens': self.count_tokens(current_chunk)
            })

        return chunks

    def count_tokens(self, text: str) -> int:
        """Подсчет токенов в тексте"""
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            return len(text) // 4


class KnowledgeBase:
    """Класс для работы с векторной базой знаний"""

    def __init__(self, openai_client: OpenAI, embedding_model: str = "text-embedding-ada-002"):
        self.client = openai_client
        self.embedding_model = embedding_model
        self.index = None
        self.chunks = []
        self.metadatas = []

    def get_embedding(self, text: str) -> List[float]:
        """Получение эмбеддинга для текста"""
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logging.error(f"Ошибка получения эмбеддинга: {e}")
            # Возвращаем случайный эмбеддинг как fallback
            return np.random.rand(1536).tolist()

    def save_metadata_to_file(self, file_path: str):
        """
        Сохранение всех метаданных в отдельный читаемый файл.
        """
        try:
            # Создаем имя файла для читаемых метаданных
            base_name = os.path.splitext(file_path)[0]  # Убираем расширение .index
            metadata_file = base_name + '_metadata.json'

            # Подготавливаем данные для сохранения
            metadata_to_save = {
                'timestamp': datetime.now().isoformat(),
                'embedding_model': self.embedding_model,
                'total_chunks': len(self.chunks),
                'chunks': []
            }

            # Собираем информацию о каждом чанке
            for i, chunk in enumerate(self.chunks):
                chunk_info = {
                    'chunk_id': i,
                    'content_preview': chunk['content'][:200] + '...' if len(chunk['content']) > 200 else chunk[
                        'content'],
                    'tokens': chunk.get('tokens', 0),
                    'metadata': chunk.get('metadata', {})
                }
                metadata_to_save['chunks'].append(chunk_info)

            # Сохраняем в JSON файл
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_to_save, f, ensure_ascii=False, indent=2)

            logging.info(f"Метаданные сохранены в файл: {metadata_file}")
            return True

        except Exception as e:
            logging.error(f"Ошибка при сохранении метаданных: {e}")
            return False

    def save_metadata_statistics(self, file_path: str):
        """
        Сохранение статистики по метаданным в отдельный файл.
        """
        try:
            # Создаем имя файла для статистики
            base_name = os.path.splitext(file_path)[0]  # Убираем расширение .index
            stats_file = base_name + '_statistics.json'

            # Собираем статистику
            statistics = {
                'timestamp': datetime.now().isoformat(),
                'total_chunks': len(self.chunks),
                'total_tokens': sum(chunk.get('tokens', 0) for chunk in self.chunks),
                'sources': {},
                'document_titles': {},
                'headers': {}
            }

            # Анализируем источники
            sources = {}
            document_titles = {}
            headers = {}

            for chunk in self.chunks:
                metadata = chunk.get('metadata', {})

                # Статистика по источникам
                source = metadata.get('source', 'unknown')
                sources[source] = sources.get(source, 0) + 1

                # Статистика по названиям документов
                doc_title = metadata.get('document_title', 'unknown')
                document_titles[doc_title] = document_titles.get(doc_title, 0) + 1

                # Статистика по заголовкам
                header = metadata.get('header', 'unknown')
                headers[header] = headers.get(header, 0) + 1

            statistics['sources'] = dict(sorted(sources.items(), key=lambda x: x[1], reverse=True))
            statistics['document_titles'] = dict(sorted(document_titles.items(), key=lambda x: x[1], reverse=True))
            statistics['headers'] = dict(sorted(headers.items(), key=lambda x: x[1], reverse=True))

            # Сохраняем статистику
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(statistics, f, ensure_ascii=False, indent=2)

            logging.info(f"Статистика сохранена в файл: {stats_file}")
            return True

        except Exception as e:
            logging.error(f"Ошибка при сохранении статистики: {e}")
            return False

    def build_from_documents(self, documents: List[Dict[str, Any]]):
        """Построение векторной базы из документов"""
        if not documents:
            raise ValueError("Нет документов для построения базы знаний")

        self.chunks = documents
        self.metadatas = [doc['metadata'] for doc in documents]

        # Получаем эмбеддинги для всех чанков
        logging.info("Получение эмбеддингов для документов...")
        embeddings = []
        for i, doc in enumerate(documents):
            if i % 10 == 0:
                logging.info(f"Обработано {i}/{len(documents)} документов")
            embedding = self.get_embedding(doc['content'])
            embeddings.append(embedding)

        # Создаем FAISS индекс
        embeddings_array = np.array(embeddings).astype('float32')
        dimension = embeddings_array.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings_array)

        logging.info(f"База знаний построена: {len(documents)} документов, {dimension} измерений")

    def save_to_file(self, file_path: str):
        """Сохранение базы знаний в файл"""
        if self.index is None:
            raise ValueError("База знаний не построена")

        # Создаем директорию если не существует
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)

        # Сохраняем FAISS индекс
        faiss.write_index(self.index, file_path)

        # Сохраняем метаданные в бинарный файл (для быстрой загрузки)
        # Используем оригинальное имя файла с расширением .metadata
        metadata_file = file_path + '.metadata'
        with open(metadata_file, 'wb') as f:
            pickle.dump({
                'chunks': self.chunks,
                'metadatas': self.metadatas,
                'embedding_model': self.embedding_model
            }, f)

        # Сохраняем метаданные в читаемый JSON файл (дополнительно)
        self.save_metadata_to_file(file_path)

        # Сохраняем статистику (дополнительно)
        self.save_metadata_statistics(file_path)

        logging.info(f"База знаний сохранена в {file_path}")

    def load_from_file(self, file_path: str) -> bool:
        """Загрузка базы знаний из файла"""
        if not os.path.exists(file_path):
            logging.warning(f"Файл базы знаний {file_path} не существует")
            return False

        try:
            # Загружаем FAISS индекс
            self.index = faiss.read_index(file_path)

            # Загружаем метаданные из бинарного файла
            # Используем оригинальное имя файла с расширением .metadata
            metadata_file = file_path + '.metadata'
            if os.path.exists(metadata_file):
                with open(metadata_file, 'rb') as f:
                    metadata = pickle.load(f)
                    self.chunks = metadata.get('chunks', [])
                    self.metadatas = metadata.get('metadatas', [])
                    self.embedding_model = metadata.get('embedding_model', self.embedding_model)

                logging.info(f"База знаний загружена из {file_path}: {len(self.chunks)} документов")
                return True
            else:
                # Пробуем загрузить из JSON файла как fallback
                base_name = os.path.splitext(file_path)[0]
                json_metadata_file = base_name + '_metadata.json'

                if os.path.exists(json_metadata_file):
                    logging.info(f"Попытка загрузки метаданных из JSON файла: {json_metadata_file}")
                    with open(json_metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    # Восстанавливаем структуру chunks из JSON
                    self.chunks = []
                    for chunk_info in metadata.get('chunks', []):
                        self.chunks.append({
                            'content': chunk_info.get('content_preview', ''),  # Внимание: здесь только превью!
                            'metadata': chunk_info.get('metadata', {}),
                            'tokens': chunk_info.get('tokens', 0)
                        })

                    self.metadatas = [chunk['metadata'] for chunk in self.chunks]
                    self.embedding_model = metadata.get('embedding_model', self.embedding_model)

                    logging.warning(f"Метаданные загружены из JSON, но содержимое чанков может быть неполным")
                    return True
                else:
                    logging.error(f"Файл метаданных {metadata_file} не найден")
                    return False

        except Exception as e:
            logging.error(f"Ошибка загрузки базы знаний из {file_path}: {e}")
            return False

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Поиск в базе знаний"""
        if self.index is None or len(self.chunks) == 0:
            return []

        query_embedding = self.get_embedding(query)
        query_array = np.array([query_embedding]).astype('float32')

        # Ищем k ближайших соседей
        distances, indices = self.index.search(query_array, min(k, len(self.chunks)))

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.chunks):
                results.append({
                    'content': self.chunks[idx]['content'],
                    'metadata': self.metadatas[idx],
                    'distance': float(distances[0][i])
                })

        return results

    def get_metadata_info(self) -> Dict[str, Any]:
        """
        Получение информации о метаданных базы знаний.
        """
        if not self.chunks:
            return {'status': 'empty', 'total_chunks': 0}

        # Собираем уникальные источники и заголовки
        sources = set()
        document_titles = set()
        headers = set()

        for chunk in self.chunks:
            metadata = chunk.get('metadata', {})
            sources.add(metadata.get('source', 'unknown'))
            document_titles.add(metadata.get('document_title', 'unknown'))
            headers.add(metadata.get('header', 'unknown'))

        return {
            'status': 'loaded',
            'total_chunks': len(self.chunks),
            'unique_sources': len(sources),
            'unique_document_titles': len(document_titles),
            'unique_headers': len(headers),
            'sources_list': list(sources)[:10],  # Ограничиваем список для читаемости
            'document_titles_list': list(document_titles)[:10],
            'total_tokens': sum(chunk.get('tokens', 0) for chunk in self.chunks)
        }

class Assistant:
    """Основной класс ассистента"""
    
    def __init__(self, config_path: str = "config.json", prompts_path: str = "prompts.json"):
        # Загрузка конфигурации
        self.config = self.load_config(config_path)
        self.prompts = self.load_config(prompts_path)
        
        # Настройка логирования
        self._setup_logging()
        
        # Инициализация OpenAI клиента
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY не установлен")
        self.client = OpenAI(api_key=api_key)
        
        # Параметры GPT и эмбеддингов
        self.gpt_model = self.config['gpt']['model']
        self.gpt_max_tokens = self.config['gpt']['max_tokens']
        self.gpt_temperature = self.config['gpt']['temperature']
        self.embedding_model = self.config['embedding']['model']
        
        # Параметр количества релевантных документов для поиска
        self.search_k = self.config['knowledge_base'].get('search_k', 5)
        
        # Инициализация компонентов
        self.processor = DocumentProcessor(
            chunk_size=self.config['knowledge_base']['chunk_size'],
            chunk_overlap=self.config['knowledge_base']['chunk_overlap']
        )
        self.knowledge_base = KnowledgeBase(self.client, self.embedding_model)
        
        # Построение или загрузка базы знаний
        self.build_or_load_knowledge_base()
    
    def _setup_logging(self):
        """Настройка логирования"""
        log_config = self.config.get('logging', {})
        if log_config.get('enabled', True):
            log_file = log_config.get('log_file', 'assistant.log')
            log_level = getattr(logging, log_config.get('level', 'INFO'))
            
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, encoding='utf-8'),
                    logging.StreamHandler()
                ]
            )
        else:
            logging.basicConfig(level=logging.WARNING, handlers=[logging.StreamHandler()])
        
        logging.info("Логирование инициализировано")
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Загрузка конфигурации из JSON файла"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Файл конфигурации {config_path} не найден")
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка в формате JSON файла {config_path}: {e}")
    
    def build_or_load_knowledge_base(self):
        """Построение или загрузка базы знаний"""
        index_path = self.config['knowledge_base']['index_path']
        
        # Пытаемся загрузить существующую базу
        if os.path.exists(index_path):
            logging.info(f"Попытка загрузки базы знаний из {index_path}")
            if self.knowledge_base.load_from_file(index_path):
                logging.info("База знаний успешно загружена из файла")
                return
        
        # Если загрузка не удалась, строим новую базу
        logging.info("Создание новой базы знаний...")
        self.build_knowledge_base()
        
        # Сохраняем новую базу
        if self.knowledge_base.index is not None:
            self.knowledge_base.save_to_file(index_path)

    def build_knowledge_base(self):
        """Построение базы знаний из файлов"""
        data_path = self.config['knowledge_base']['data_path']
        extensions = self.config['knowledge_base']['extensions']
        use_markdown = self.config['knowledge_base'].get('use_markdown_processing', False)

        if not os.path.exists(data_path):
            logging.warning(f"Директория {data_path} не существует")
            return

        all_documents = []

        # Сканируем директорию на наличие файлов
        for ext in extensions:
            pattern = f"**/*.{ext}"
            files = list(Path(data_path).glob(pattern))

            for file_path in files:
                try:
                    logging.info(f"Обработка файла: {file_path}")

                    if ext == 'pdf':
                        text = self.processor.read_pdf_file(str(file_path))
                    else:
                        text = self.processor.read_text_file(str(file_path))

                    # Разбиваем текст на чанки с учетом настройки markdown обработки
                    chunks = self.processor.split_text(text, file_path.name, use_markdown=use_markdown)
                    all_documents.extend(chunks)

                except Exception as e:
                    logging.error(f"Ошибка при обработке файла {file_path}: {e}")
                    continue

        if not all_documents:
            logging.warning("Не найдено документов для обработки")
            return

        # Строим векторную базу
        self.knowledge_base.build_from_documents(all_documents)
        logging.info(f"База знаний успешно построена из {len(all_documents)} фрагментов")

    def ask_question(self, question: str, temperature: float = None) -> Dict[str, Any]:
        """Задать вопрос ассистенту"""
        start_time = datetime.now()
        try:
            # Логируем вопрос
            logging.info(f"Вопрос: {question}")
            
            # Поиск релевантных документов с параметром k из конфига
            relevant_docs = self.knowledge_base.search(question, k=self.search_k)
            
            if not relevant_docs:
                response = {
                    'answer': self.prompts['error_responses']['no_documents'],
                    'sources': [],
                    'tokens_used': 0,
                    'error': 'no_documents'
                }
                logging.warning("Не найдено релевантных документов")
                return response
            
            # Формируем контекст из найденных документов
            context = "\n\n".join([
                f"Фрагмент {i+1} (metadata: {doc['metadata']}):\n{doc['content']}"
                for i, doc in enumerate(relevant_docs)
            ])
            
            # Системный промпт
            system_prompt = self.prompts['system_prompt']
            
            # Формируем сообщения для ChatGPT
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Контекст для ответа:\n{context}\n\nВопрос: {question}"}
            ]
            
            # Используем температуру из параметра или из конфига
            temp = temperature if temperature is not None else self.gpt_temperature
            
            # Отправляем запрос к ChatGPT
            response = self.client.chat.completions.create(
                model=self.gpt_model,
                messages=messages,
                temperature=temp,
                max_tokens=self.gpt_max_tokens
            )
            
            answer = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            # Формируем информацию об источниках
            sources = [
                {
                    'source': doc['metadata']['source'],
                    'content_preview': doc['content'][:200] + '...' if len(doc['content']) > 200 else doc['content'],
                    'relevance_score': 1 - doc['distance']  # Преобразуем расстояние в оценку релевантности
                }
                for doc in relevant_docs
            ]
            
            response_data = {
                'answer': answer,
                'sources': sources,
                'tokens_used': tokens_used,
                'question': question
            }
            
            # Логируем успешный ответ
            processing_time = (datetime.now() - start_time).total_seconds()
            logging.info(f"Ответ успешно сгенерирован: {tokens_used} токенов, время: {processing_time:.2f}с")
            logging.debug(f"Ответ: {answer[:200]}...")
            
            return response_data
            
        except Exception as e:
            # Логируем ошибку
            error_msg = f"Ошибка при обработке вопроса: {e}"
            logging.error(error_msg)
            
            return {
                'answer': self.prompts['error_responses']['processing_error'],
                'sources': [],
                'tokens_used': 0,
                'error': str(e)
            }
    
    def summarize_dialog(self, dialog: str) -> str:
        """Суммаризация диалога"""
        start_time = datetime.now()
        try:
            logging.info("Запрос на суммаризацию диалога")
            
            messages = [
                {"role": "system", "content": self.prompts['summarize_prompt']},
                {"role": "user", "content": dialog}
            ]
            
            response = self.client.chat.completions.create(
                model=self.gpt_model,
                messages=messages,
                temperature=0.0,
                max_tokens=500
            )
            
            summary = response.choices[0].message.content
            
            # Логируем суммаризацию
            processing_time = (datetime.now() - start_time).total_seconds()
            logging.info(f"Суммаризация выполнена: время {processing_time:.2f}с")
            
            return summary
            
        except Exception as e:
            error_msg = f"Ошибка при суммаризации: {e}"
            logging.error(error_msg)
            return "Не удалось выполнить суммаризацию диалога."

    def get_knowledge_base_info(self) -> Dict[str, Any]:
        """Получение информации о базе знаний"""
        base_info = {
            'name': self.config['knowledge_base']['name'],
            'description': self.config['knowledge_base']['description'],
            'documents_count': len(self.knowledge_base.chunks) if self.knowledge_base.chunks else 0,
            'data_path': self.config['knowledge_base']['data_path'],
            'index_path': self.config['knowledge_base']['index_path'],
            'status': 'loaded' if self.knowledge_base.index else 'empty',
            'gpt_model': self.gpt_model,
            'embedding_model': self.embedding_model,
            'search_k': self.search_k
        }

        # Добавляем информацию о метаданных
        metadata_info = self.knowledge_base.get_metadata_info()
        base_info.update(metadata_info)

        return base_info

    def rebuild_knowledge_base(self) -> Dict[str, Any]:
        """Перестроить базу знаний"""
        logging.info("Запущено перестроение базы знаний")
        
        # Строим новую базу
        self.build_knowledge_base()
        
        # Сохраняем новую базу
        index_path = self.config['knowledge_base']['index_path']
        if self.knowledge_base.index is not None:
            self.knowledge_base.save_to_file(index_path)
            status = "success"
            message = f"База знаний успешно перестроена: {len(self.knowledge_base.chunks)} документов"
        else:
            status = "error"
            message = "Не удалось перестроить базу знаний"
        
        logging.info(message)
        return {'status': status, 'message': message, 'documents_count': len(self.knowledge_base.chunks)}