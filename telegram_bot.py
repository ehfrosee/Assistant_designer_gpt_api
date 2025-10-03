# -*- coding: utf-8 -*-
"""Telegram Bot для нейро-консультанта по проектной документации"""

import os
import json
import requests
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация API
API_BASE_URL = os.getenv('API_BASE_URL', 'http://127.0.0.1:5000')

@dataclass
class UserSession:
    """Данные сессии пользователя"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    question_history: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_question(self, question: str, answer: str, tokens_used: int, sources: List[Dict]):
        """Добавить вопрос в историю"""
        self.question_history.append({
            'timestamp': datetime.now(),
            'question': question,
            'answer': answer,
            'tokens_used': tokens_used,
            'sources': sources
        })
        
        # Ограничиваем историю последними 50 вопросами
        if len(self.question_history) > 50:
            self.question_history = self.question_history[-50:]

class NeuroConsultantBot:
    """Класс Telegram бота для нейро-консультанта"""
    
    def __init__(self, token: str, config_path: str = "config.json"):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.user_sessions: Dict[int, UserSession] = {}
        self.admin_ids = self._load_admin_ids(config_path)
        
        # Регистрация обработчиков
        self._setup_handlers()
    
    def _load_admin_ids(self, config_path: str) -> List[int]:
        """Загрузка ID администраторов из config.json"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Получаем admin_ids из конфига, по умолчанию [1961734606]
            admin_ids = config.get('telegram_bot', {}).get('admin_ids', [1961734606])
            
            # Убеждаемся, что это список чисел
            if isinstance(admin_ids, list):
                return [int(admin_id) for admin_id in admin_ids]
            else:
                logger.warning(f"admin_ids должен быть списком, получен: {type(admin_ids)}")
                return [1961734606]
                
        except FileNotFoundError:
            logger.warning(f"Файл конфигурации {config_path} не найден, используются admin_ids по умолчанию")
            return [1961734606]
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка чтения config.json: {e}, используются admin_ids по умолчанию")
            return [1961734606]
        except Exception as e:
            logger.error(f"Ошибка загрузки admin_ids: {e}, используются admin_ids по умолчанию")
            return [1961734606]
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return user_id in self.admin_ids
    
    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        # Обработчики команд
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("info", self._info_command))
        self.application.add_handler(CommandHandler("stats", self._stats_command))
        self.application.add_handler(CommandHandler("clear", self._clear_command))
        self.application.add_handler(CommandHandler("summarize", self._summarize_command))
        self.application.add_handler(CommandHandler("rebuild", self._rebuild_command))
        
        # Обработчик callback запросов (кнопки)
        self.application.add_handler(CallbackQueryHandler(self._button_handler))
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        
        # Обработчик ошибок
        self.application.add_error_handler(self._error_handler)
    
    def _get_user_session(self, user_id: int, username: str = None, first_name: str = None) -> UserSession:
        """Получение или создание сессии пользователя"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSession(
                user_id=user_id,
                username=username,
                first_name=first_name
            )
        else:
            # Обновляем данные пользователя если нужно
            if username and not self.user_sessions[user_id].username:
                self.user_sessions[user_id].username = username
            if first_name and not self.user_sessions[user_id].first_name:
                self.user_sessions[user_id].first_name = first_name
        
        return self.user_sessions[user_id]
    
    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Универсальный метод для API запросов"""
        url = f"{API_BASE_URL}/api{endpoint}"
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API connection error: {e}")
            return None
    
    def _escape_html(self, text: str) -> str:
        """Экранирование символов HTML"""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;'))
    
    def _split_message(self, text: str, max_length: int = 4000) -> List[str]:
        """Разбивает сообщение на части с учетом границ предложений"""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        # Разбиваем по абзацам
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # Если добавление параграфа не превысит лимит
            if len(current_part) + len(paragraph) + 2 <= max_length:
                if current_part:
                    current_part += "\n\n" + paragraph
                else:
                    current_part = paragraph
            else:
                # Если текущая часть не пустая, сохраняем её
                if current_part:
                    parts.append(current_part)
                    current_part = ""
                
                # Если параграф сам по себе слишком длинный, разбиваем его
                if len(paragraph) > max_length:
                    sentences = paragraph.split('. ')
                    current_sentence = ""
                    
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        
                        if len(current_sentence) + len(sentence) + 2 <= max_length:
                            if current_sentence:
                                current_sentence += ". " + sentence
                            else:
                                current_sentence = sentence + "."
                        else:
                            if current_sentence:
                                parts.append(current_sentence)
                                current_sentence = sentence + "."
                            else:
                                # Если одно предложение слишком длинное, разбиваем принудительно
                                parts.append(sentence[:max_length-3] + "...")
                                current_sentence = "..." + sentence[max_length-3:] + "."
                    
                    if current_sentence:
                        parts.append(current_sentence)
                else:
                    parts.append(paragraph)
        
        if current_part:
            parts.append(current_part)
        
        return parts
    
    async def _safe_reply_text(self, update: Update, text: str, **kwargs):
        """Безопасная отправка сообщения с обработкой ошибок"""
        try:
            await update.message.reply_text(text, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            # Пробуем отправить без форматирования
            clean_text = text.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')
            await update.message.reply_text(clean_text)
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        user = update.message.from_user
        session = self._get_user_session(user.id, user.username, user.first_name)
        
        # Проверяем доступность API и базы знаний
        health_data = self._make_api_request("GET", "/health")
        kb_info = self._make_api_request("GET", "/knowledge-base/info")
        
        if health_data and health_data.get('status') == 'healthy':
            api_status = "✅ API доступен"
            if kb_info:
                docs_count = kb_info.get('documents_count', 0)
                kb_status = f"✅ База знаний загружена ({docs_count} документов)"
                gpt_model = self._escape_html(kb_info.get('gpt_model', 'Unknown'))
                embedding_model = self._escape_html(kb_info.get('embedding_model', 'Unknown'))
            else:
                kb_status = "❌ Информация о базе знаний недоступна"
                gpt_model = "Unknown"
                embedding_model = "Unknown"
        else:
            api_status = "❌ API недоступен"
            kb_status = "❌ База знаний не загружена"
            gpt_model = "Unknown"
            embedding_model = "Unknown"
        
        welcome_text = f"""
<b>🤖 Добро пожаловать в нейро-консультант по проектной документации!</b>

{api_status}
{kb_status}

<b>Модели:</b>
• GPT: {gpt_model}
• Эмбеддинги: {embedding_model}

Я помогу вам найти ответы на вопросы по проектной документации. Просто задайте вопрос, и я найду relevantную информацию в базе знаний.

<b>Основные команды:</b>
/info - Информация о базе знаний
/stats - Статистика ваших запросов
/summarize - Суммаризировать историю диалога
/clear - Очистить историю вопросов
/rebuild - Перестроить базу знаний (админ)
/help - Справка по использованию

<b>Примеры вопросов:</b>
• Какие требования к пожарной сигнализации?
• Перечислите используемые материалы
• Опишите структуру системы электроснабжения
        """
        
        await self._safe_reply_text(update, welcome_text, parse_mode='HTML')
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        help_text = """
<b>📖 Справка по использованию бота</b>

<b>Как работать с ботом:</b>

1. <i>Задавайте вопросы</i> - просто напишите ваш вопрос по проектной документации
2. <i>Получайте ответы</i> - бот найдет relevantную информацию в базе знаний
3. <i>Изучайте источники</i> - каждый ответ содержит ссылки на исходные документы

<b>Команды:</b>
/start - Начать работу с ботом
/info - Информация о базе знаний
/stats - Статистика ваших запросов
/summarize - Суммаризировать историю диалога
/clear - Очистить историю вопросов
/rebuild - Перестроить базу знаний (только для администраторов)
/help - Эта справка

<b>Особенности:</b>
• Бот использует только информацию из загруженных документов
• Каждый ответ содержит оценку достоверности
• История вопросов сохраняется в течение сессии
• База знаний автоматически сохраняется и загружается
        """
        
        await self._safe_reply_text(update, help_text, parse_mode='HTML')
    
    async def _info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /info - информация о базе знаний"""
        kb_info = self._make_api_request("GET", "/knowledge-base/info")
        
        if not kb_info:
            await update.message.reply_text("❌ Не удалось получить информацию о базе знаний")
            return
        
        info_text = f"""
<b>📚 Информация о базе знаний</b>

<b>Название:</b> {self._escape_html(kb_info.get('name', 'Не указано'))}
<b>Описание:</b> {self._escape_html(kb_info.get('description', 'Не указано'))}
<b>Путь к данным:</b> {self._escape_html(kb_info.get('data_path', 'Не указан'))}
<b>Файл индекса:</b> {self._escape_html(kb_info.get('index_path', 'Не указан'))}
<b>Количество документов:</b> {kb_info.get('documents_count', 0)}
<b>Статус:</b> {kb_info.get('status', 'unknown')}
<b>GPT модель:</b> {self._escape_html(kb_info.get('gpt_model', 'Не указана'))}
<b>Модель эмбеддингов:</b> {self._escape_html(kb_info.get('embedding_model', 'Не указана'))}

База знаний автоматически загружается при запуске системы.
Для перестроения базы используйте команду /rebuild
        """
        
        # Создаем клавиатуру с кнопками
        keyboard = [
            [InlineKeyboardButton("🔄 Перестроить базу", callback_data="rebuild_kb")],
            [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(info_text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def _stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /stats - статистика пользователя"""
        user = update.message.from_user
        session = self._get_user_session(user.id)
        
        total_questions = len(session.question_history)
        total_tokens = sum(qa.get('tokens_used', 0) for qa in session.question_history)
        
        if total_questions == 0:
            await update.message.reply_text("📊 Вы еще не задавали вопросов")
            return
        
        # Анализ источников
        source_stats = {}
        for qa in session.question_history:
            for source in qa.get('sources', []):
                source_name = source.get('source', 'Unknown')
                source_stats[source_name] = source_stats.get(source_name, 0) + 1
        
        common_sources = sorted(source_stats.items(), key=lambda x: x[1], reverse=True)[:3]
        sources_text = ", ".join([f"{self._escape_html(source)}({count})" for source, count in common_sources])
        
        # Средняя релевантность
        avg_relevance = 0
        relevance_count = 0
        for qa in session.question_history:
            for source in qa.get('sources', []):
                relevance = source.get('relevance_score', 0)
                if relevance:
                    avg_relevance += relevance
                    relevance_count += 1
        
        avg_relevance_pct = int((avg_relevance / relevance_count) * 100) if relevance_count > 0 else 0
        
        stats_text = f"""
<b>📊 Ваша статистика</b>

<b>Всего вопросов:</b> {total_questions}
<b>Использовано токенов:</b> {total_tokens}
<b>Средняя длина ответа:</b> {total_tokens // total_questions if total_questions > 0 else 0} токенов
<b>Средняя релевантность:</b> {avg_relevance_pct}%
<b>Активность с:</b> {session.created_at.strftime('%d.%m.%Y %H:%M')}
<b>Частые источники:</b> {sources_text}

<b>Последние вопросы:</b>
"""
        
        # Добавляем последние 3 вопроса
        for i, qa in enumerate(session.question_history[-3:], 1):
            preview = qa['question'][:50] + '...' if len(qa['question']) > 50 else qa['question']
            stats_text += f"\n{i}. {self._escape_html(preview)}"
        
        await self._safe_reply_text(update, stats_text, parse_mode='HTML')
    
    async def _clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /clear - очистка истории"""
        user = update.message.from_user
        session = self._get_user_session(user.id)
        
        questions_count = len(session.question_history)
        session.question_history.clear()
        
        await update.message.reply_text(f"🗑️ История очищена. Удалено {questions_count} вопросов")
    
    async def _summarize_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /summarize - суммаризация диалога"""
        user = update.message.from_user
        session = self._get_user_session(user.id)
        
        if len(session.question_history) == 0:
            await update.message.reply_text("📝 История вопросов пуста")
            return
        
        # Формируем диалог для суммаризации
        dialog_text = f"Диалог пользователя {user.first_name or user.username or 'Unknown'}:\n\n"
        for i, qa in enumerate(session.question_history, 1):
            dialog_text += f"Вопрос {i}: {qa['question']}\n"
            dialog_text += f"Ответ {i}: {qa['answer'][:300]}...\n\n"
        
        # Отправляем сообщение о обработке
        processing_msg = await update.message.reply_text("📊 Суммаризирую диалог...")
        
        data = self._make_api_request("POST", "/summarize", json={"dialog": dialog_text})
        
        if not data:
            await processing_msg.delete()
            await update.message.reply_text("❌ Ошибка при суммаризации диалога")
            return
        
        summary_text = f"""
<b>📋 Суммаризация диалога</b>

{self._escape_html(data['summary'])}

<b>Статистика суммаризации:</b>
• Исходный текст: {data['original_length']} символов
• Суммаризация: {data['summary_length']} символов
• Коэффициент сжатия: {data['summary_length']/data['original_length']:.1%}
        """
        
        await processing_msg.delete()
        await self._safe_reply_text(update, summary_text, parse_mode='HTML')
    
    async def _rebuild_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /rebuild - перестроение базы знаний"""
        # Проверяем права администратора
        if not self._is_admin(update.message.from_user.id):
            await update.message.reply_text("❌ Эта команда доступна только администраторам")
            return
        
        # Отправляем сообщение о обработке
        processing_msg = await update.message.reply_text("🔄 Перестраиваю базу знаний...")
        
        data = self._make_api_request("POST", "/knowledge-base/rebuild")
        
        if not data:
            await processing_msg.delete()
            await update.message.reply_text("❌ Ошибка при перестроении базы знаний")
            return
        
        if data.get('status') == 'success':
            result_text = f"""
<b>✅ База знаний перестроена</b>

{self._escape_html(data.get('message', 'Успешно'))}
<b>Документов в базе:</b> {data.get('documents_count', 0)}
            """
        else:
            result_text = f"""
<b>❌ Ошибка перестроения базы</b>

{self._escape_html(data.get('message', 'Неизвестная ошибка'))}
            """
        
        await processing_msg.delete()
        await self._safe_reply_text(update, result_text, parse_mode='HTML')
    
    async def _button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        if query.data == "rebuild_kb":
            # Проверяем права администратора
            if not self._is_admin(user.id):
                await query.edit_message_text("❌ Эта операция доступна только администраторам")
                return
            
            # Показываем подтверждение
            keyboard = [
                [InlineKeyboardButton("✅ Да, перестроить", callback_data="confirm_rebuild")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_rebuild")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ <b>Подтверждение перестроения базы знаний</b>\n\n"
                "Это действие перестроит векторную базу знаний из исходных документов. "
                "Процесс может занять несколько минут. Продолжить?",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        elif query.data == "confirm_rebuild":
            await query.edit_message_text("🔄 Перестраиваю базу знаний...")
            
            data = self._make_api_request("POST", "/knowledge-base/rebuild")
            
            if data and data.get('status') == 'success':
                result_text = f"✅ База знаний перестроена\n{data.get('message')}"
            else:
                result_text = "❌ Ошибка при перестроении базы знаний"
            
            await query.edit_message_text(result_text)
        
        elif query.data == "cancel_rebuild":
            await query.edit_message_text("❌ Перестроение базы знаний отменено")
        
        elif query.data == "show_stats":
            user = query.from_user
            session = self._get_user_session(user.id)
            
            total_questions = len(session.question_history)
            if total_questions == 0:
                await query.edit_message_text("📊 Вы еще не задавали вопросов")
                return
            
            total_tokens = sum(qa.get('tokens_used', 0) for qa in session.question_history)
            
            stats_text = f"""
<b>📊 Ваша статистика</b>

<b>Всего вопросов:</b> {total_questions}
<b>Использовано токенов:</b> {total_tokens}
<b>Средняя длина ответа:</b> {total_tokens // total_questions} токенов
<b>Активность с:</b> {session.created_at.strftime('%d.%m.%Y %H:%M')}
            """
            
            await query.edit_message_text(stats_text, parse_mode='HTML')
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик текстовых сообщений (вопросов)"""
        user = update.message.from_user
        session = self._get_user_session(user.id, user.username, user.first_name)
        question = update.message.text
        
        # Пропускаем короткие сообщения (возможно, команды)
        if len(question.strip()) < 3:
            await update.message.reply_text(
                "❓ Вопрос слишком короткий. Пожалуйста, сформулируйте вопрос подробнее.",
                reply_to_message_id=update.message.message_id
            )
            return
        
        # Отправляем сообщение о обработке
        processing_msg = await update.message.reply_text("🔍 Ищу ответ в документации...")
        
        # Отправляем вопрос в API
        data = self._make_api_request(
            "POST", 
            "/ask",
            json={
                "question": question
            }
        )
        
        if not data:
            await processing_msg.delete()
            await update.message.reply_text(
                "❌ Ошибка при обработке вопроса. Попробуйте позже.",
                reply_to_message_id=update.message.message_id
            )
            return
        
        # Сохраняем в историю
        session.add_question(question, data['answer'], data['tokens_used'], data.get('sources', []))
        
        # Очищаем ответ и источники
        safe_answer = self._escape_html(data['answer'])
        
        # Форматируем ответ с HTML разметкой
        response_text = f"""
<b>🤖 Ответ:</b>

{safe_answer}
        """
        
        # Добавляем информацию об источниках если они есть
        sources = data.get('sources', [])
        if sources:
            response_text += "\n<b>📚 Источники информации:</b>\n"
            for i, source in enumerate(sources[:3], 1):
                relevance_percent = int((source.get('relevance_score', 0) or 0) * 100)
                source_name = self._escape_html(source.get('source', 'Неизвестный источник'))
                response_text += f"\n{i}. 📄 {source_name}"
                response_text += f" (релевантность: {relevance_percent}%)"
        
        response_text += f"""

<b>📊 Статистика запроса:</b>
• Использовано токенов: {data['tokens_used']}
• Всего вопросов в сессии: {len(session.question_history)}
• Источников найдено: {len(sources)}
        """
        
        await processing_msg.delete()
        
        # Если ответ слишком длинный, разбиваем на части
        if len(response_text) > 4000:
            parts = self._split_message(response_text)
            
            for i, part in enumerate(parts):
                try:
                    if i == 0:
                        await update.message.reply_text(part, parse_mode='HTML')
                    else:
                        continuation_text = f"<b>(продолжение {i+1}/{len(parts)})</b>\n{part}"
                        await update.message.reply_text(continuation_text, parse_mode='HTML')
                except Exception as e:
                    logger.error(f"Ошибка при отправке части {i}: {e}")
                    # Пробуем отправить без HTML
                    clean_text = part.replace('<b>', '').replace('</b>', '')
                    await update.message.reply_text(clean_text)
        else:
            try:
                await update.message.reply_text(response_text, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Ошибка отправки HTML: {e}")
                # Fallback: отправляем без форматирования
                clean_text = response_text.replace('<b>', '').replace('</b>', '')
                await update.message.reply_text(clean_text)
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        if update and update.message:
            try:
                await update.message.reply_text(
                    "❌ Произошла ошибка при обработке запроса. Попробуйте позже или обратитесь к администратору."
                )
            except:
                pass
    
    def run(self):
        """Запуск бота"""
        logger.info(f"Бот запущен. Администраторы: {self.admin_ids}")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Основная функция"""
    # Получение токена бота из переменных окружения
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
        print("Пожалуйста, установите переменную окружения TELEGRAM_BOT_TOKEN")
        return
    
    # Создание и запуск бота
    bot = NeuroConsultantBot(bot_token)
    
    print("=" * 50)
    print("Telegram Bot для нейро-консультанта")
    print("=" * 50)
    print(f"API сервер: {API_BASE_URL}")
    print(f"Bot Token: {'установлен' if bot_token else 'отсутствует'}")
    print(f"Администраторы: {bot.admin_ids}")
    print("Бот запускается...")
    print("=" * 50)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nБот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        print(f"Критическая ошибка: {e}")

if __name__ == '__main__':
    main()