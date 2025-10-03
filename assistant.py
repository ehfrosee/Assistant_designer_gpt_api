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
    
    def split_text(self, text: str, filename: str) -> List[Dict[str, Any]]:
        """Разделение текста на чанки"""
        if not text.strip():
            return []
        
        # Простой сплиттер по предложениям и абзацам
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
                        'metadata': {'source': filename},
                        'tokens': self.count_tokens(current_chunk)
                    })
                
                # Если параграф сам по себе больше chunk_size, разбиваем его
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
                                    'metadata': {'source': filename},
                                    'tokens': self.count_tokens(current_chunk)
                                })
                            current_chunk = sentence
                else:
                    current_chunk = paragraph
        
        if current_chunk:
            chunks.append({
                'content': current_chunk,
                'metadata': {'source': filename},
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
        
        # Сохраняем метаданные в отдельный файл
        metadata_file = file_path + '.metadata'
        with open(metadata_file, 'wb') as f:
            pickle.dump({
                'chunks': self.chunks,
                'metadatas': self.metadatas,
                'embedding_model': self.embedding_model
            }, f)
        
        logging.info(f"База знаний сохранена в {file_path}")
    
    def load_from_file(self, file_path: str) -> bool:
        """Загрузка базы знаний из файла"""
        if not os.path.exists(file_path):
            logging.warning(f"Файл базы знаний {file_path} не существует")
            return False
        
        try:
            # Загружаем FAISS индекс
            self.index = faiss.read_index(file_path)
            
            # Загружаем метаданные
            metadata_file = file_path + '.metadata'
            if os.path.exists(metadata_file):
                with open(metadata_file, 'rb') as f:
                    metadata = pickle.load(f)
                    self.chunks = metadata.get('chunks', [])
                    self.metadatas = metadata.get('metadatas', [])
                    self.embedding_model = metadata.get('embedding_model', self.embedding_model)
            else:
                logging.warning(f"Файл метаданных {metadata_file} не найден")
                return False
            
            logging.info(f"База знаний загружена из {file_path}: {len(self.chunks)} документов")
            return True
            
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
                    
                    # Разбиваем текст на чанки
                    chunks = self.processor.split_text(text, file_path.name)
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
            
            # Поиск релевантных документов
            relevant_docs = self.knowledge_base.search(question, k=5)
            
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
                f"Документ {i+1} (источник: {doc['metadata']['source']}):\n{doc['content']}"
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
        return {
            'name': self.config['knowledge_base']['name'],
            'description': self.config['knowledge_base']['description'],
            'documents_count': len(self.knowledge_base.chunks) if self.knowledge_base.chunks else 0,
            'data_path': self.config['knowledge_base']['data_path'],
            'index_path': self.config['knowledge_base']['index_path'],
            'status': 'loaded' if self.knowledge_base.index else 'empty',
            'gpt_model': self.gpt_model,
            'embedding_model': self.embedding_model
        }
    
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