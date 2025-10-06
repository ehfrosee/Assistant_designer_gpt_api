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

from dialog_manager import DialogManager, Dialog

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
    created_at: datetime = field(default_factory=datetime.now)

class NeuroConsultantBot:
    """Класс Telegram бота для нейро-консультанта"""
    
    def __init__(self, token: str, config_path: str = "config.json", templates_path: str = "templates.json"):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.user_sessions: Dict[int, UserSession] = {}
        self.admin_ids = self._load_admin_ids(config_path)
        self.templates = self._load_templates(templates_path)
        
        # Загружаем настройки диалогов из конфига
        dialog_settings = self._load_dialog_settings(config_path)
        self.dialog_manager = DialogManager(
            storage_path="dialogs",
            max_messages=dialog_settings['max_messages'],
            max_dialogs=dialog_settings['max_dialogs']
        )
        
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
    
    def _load_dialog_settings(self, config_path: str) -> Dict:
        """Загрузка настроек диалогов из config.json"""
        default_settings = {
            'max_messages': 10,
            'max_dialogs': 50
        }
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            telegram_config = config.get('telegram_bot', {})
            return {
                'max_messages': telegram_config.get('max_messages_per_dialog', default_settings['max_messages']),
                'max_dialogs': telegram_config.get('max_dialogs_per_user', default_settings['max_dialogs'])
            }
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек диалогов: {e}, используются настройки по умолчанию")
            return default_settings
    
    def _load_templates(self, templates_path: str) -> Dict:
        """Загрузка шаблонов сообщений"""
        try:
            with open(templates_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Файл шаблонов {templates_path} не найден")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка чтения шаблонов: {e}")
            return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблонов: {e}")
            return {}
    
    def _get_template(self, category: str, key: str, default: str = "") -> str:
        """Получение шаблона по категории и ключу"""
        try:
            return self.templates.get(category, {}).get(key, default)
        except Exception as e:
            logger.error(f"Ошибка получения шаблона {category}.{key}: {e}")
            return default
    
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
        self.application.add_handler(CommandHandler("new", self._new_dialog_command))
        self.application.add_handler(CommandHandler("save", self._save_dialog_command))
        self.application.add_handler(CommandHandler("dialogs", self._list_dialogs_command))
        
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
        
        # Создаем новый диалог при старте
        dialog = self.dialog_manager.start_new_dialog(user.id, "Начало работы")
        
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
        
        welcome_text = self._get_template('start', 'welcome').format(
            api_status=api_status,
            kb_status=kb_status,
            gpt_model=gpt_model,
            embedding_model=embedding_model
        )
        
        # Добавляем информацию о диалоге
        dialog_info = f"\n\n<b>💬 Активный диалог:</b> {dialog.topic}\nДля начала новой темы используйте /new"
        welcome_text += dialog_info
        
        await self._safe_reply_text(update, welcome_text, parse_mode='HTML')
    
    async def _new_dialog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /new - начать новый диалог"""
        user = update.message.from_user
        
        # Получаем тему из аргументов команды
        topic = " ".join(context.args) if context.args else "Новая тема"
        
        # Создаем новый диалог
        dialog = self.dialog_manager.start_new_dialog(user.id, topic)
        
        response_text = f"""
<b>💬 Начата новая тема</b>

<b>Тема:</b> {self._escape_html(topic)}
<b>ID диалога:</b> {dialog.dialog_id}

Теперь вы можете задавать вопросы по новой теме.
Для сохранения диалога используйте /save
        """
        
        await self._safe_reply_text(update, response_text, parse_mode='HTML')
    
    async def _save_dialog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /save - сохранить текущий диалог"""
        user = update.message.from_user
        
        dialog = self.dialog_manager.get_active_dialog(user.id)
        if not dialog or len(dialog.messages) == 0:
            await update.message.reply_text("❌ Нет активного диалога для сохранения")
            return
        
        # Создаем summary если его нет
        if not dialog.summary and len(dialog.messages) > 1:
            # Формируем текст для суммаризации
            dialog_text = ""
            for msg in dialog.messages:
                role = "Пользователь" if msg.role == 'user' else "Ассистент"
                dialog_text += f"{role}: {msg.content}\n\n"
            
            # Отправляем на суммаризацию
            summary_data = self._make_api_request("POST", "/summarize", json={"dialog": dialog_text})
            if summary_data:
                dialog.summary = summary_data['summary']
                self.dialog_manager.update_summary(user.id, dialog.summary)
        
        # Экспортируем диалог в текстовый формат
        dialog_text = self.dialog_manager.export_dialog_text(dialog)
        
        # Сохраняем во временный файл
        filename = f"dialog_{user.id}_{dialog.dialog_id}.txt"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(dialog_text)
            
            # Отправляем файл пользователю
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"Диалог_{dialog.dialog_id}.txt",
                    caption=f"💾 Сохранен диалог: {dialog.topic}"
                )
            
            # Удаляем временный файл
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"Ошибка сохранения диалога: {e}")
            await update.message.reply_text("❌ Ошибка при сохранении диалога")
    
    async def _list_dialogs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /dialogs - список диалогов"""
        user = update.message.from_user
        
        dialogs = self.dialog_manager.get_user_dialogs(user.id)
        if not dialogs:
            await update.message.reply_text("📂 У вас пока нет сохраненных диалогов")
            return
        
        response_text = "<b>📂 Ваши диалоги:</b>\n\n"
        
        for i, dialog in enumerate(dialogs[:10], 1):  # Показываем последние 10 диалогов
            created_date = datetime.fromisoformat(dialog.created_at).strftime('%d.%m.%Y %H:%M')
            active_indicator = " 🔵" if dialog.is_active else ""
            
            response_text += f"{i}. <b>{self._escape_html(dialog.topic)}</b>\n"
            response_text += f"   📅 {created_date}{active_indicator}\n"
            if dialog.summary:
                summary_preview = dialog.summary[:100] + "..." if len(dialog.summary) > 100 else dialog.summary
                response_text += f"   📝 {self._escape_html(summary_preview)}\n"
            response_text += "\n"
        
        response_text += "Для загрузки диалога используйте /save в активном диалоге"
        
        await self._safe_reply_text(update, response_text, parse_mode='HTML')
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        help_text = (
            self._get_template('help', 'title') + "\n\n" +
            self._get_template('help', 'usage') + "\n\n" +
            self._get_template('help', 'commands') + "\n\n" +
            self._get_template('help', 'features')
        )
        
        # Добавляем команды управления диалогами
        dialog_commands = """
<b>Команды управления диалогами:</b>
/new [тема] - Начать новую тему
/save - Сохранить текущий диалог
/dialogs - Показать список диалогов
        """
        
        help_text += dialog_commands
        
        await self._safe_reply_text(update, help_text, parse_mode='HTML')
    
    async def _info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /info - информация о базе знаний"""
        kb_info = self._make_api_request("GET", "/knowledge-base/info")
        
        if not kb_info:
            await update.message.reply_text(self._get_template('errors', 'no_kb_info'))
            return
        
        info_text = self._get_template('info', 'template').format(
            name=self._escape_html(kb_info.get('name', 'Не указано')),
            description=self._escape_html(kb_info.get('description', 'Не указано')),
            data_path=self._escape_html(kb_info.get('data_path', 'Не указан')),
            index_path=self._escape_html(kb_info.get('index_path', 'Не указан')),
            documents_count=kb_info.get('documents_count', 0),
            status=kb_info.get('status', 'unknown'),
            gpt_model=self._escape_html(kb_info.get('gpt_model', 'Не указана')),
            embedding_model=self._escape_html(kb_info.get('embedding_model', 'Не указана'))
        )
        
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
        
        # Получаем все диалоги пользователя
        dialogs = self.dialog_manager.get_user_dialogs(user.id)
        total_dialogs = len(dialogs)
        
        # Получаем активный диалог
        active_dialog = self.dialog_manager.get_active_dialog(user.id)
        
        stats_text = f"""
<b>📊 Ваша статистика</b>

<b>Всего диалогов:</b> {total_dialogs}
<b>Активность с:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        
        if active_dialog:
            stats_text += f"\n<b>Текущая тема:</b> {self._escape_html(active_dialog.topic)}"
        
        await self._safe_reply_text(update, stats_text, parse_mode='HTML')
    
    async def _clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /clear - очистка истории"""
        user = update.message.from_user
        
        # Создаем новый диалог (эффективно очищает историю)
        dialog = self.dialog_manager.start_new_dialog(user.id, "Очищенная история")
        
        message = f"🗑️ История очищена. Начата новая тема: {dialog.topic}"
        await update.message.reply_text(message)
    
    async def _summarize_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /summarize - суммаризация диалога"""
        user = update.message.from_user
        
        dialog = self.dialog_manager.get_active_dialog(user.id)
        if not dialog or len(dialog.messages) == 0:
            await update.message.reply_text(self._get_template('errors', 'empty_history'))
            return
        
        # Формируем диалог для суммаризации
        dialog_text = f"Диалог пользователя {user.first_name or user.username or 'Unknown'}:\n\n"
        for i, msg in enumerate(dialog.messages, 1):
            role = "Пользователь" if msg.role == 'user' else "Ассистент"
            dialog_text += f"{role} {i}: {msg.content}\n\n"
        
        # Отправляем сообщение о обработке
        processing_msg = await update.message.reply_text(self._get_template('messages', 'summarizing'))
        
        data = self._make_api_request("POST", "/summarize", json={"dialog": dialog_text})
        
        if not data:
            await processing_msg.delete()
            await update.message.reply_text(self._get_template('errors', 'summarize_error'))
            return
        
        # Обновляем summary диалога
        self.dialog_manager.update_summary(user.id, data['summary'])
        
        summary_text = self._get_template('summarize', 'template').format(
            summary=self._escape_html(data['summary']),
            original_length=data['original_length'],
            summary_length=data['summary_length'],
            compression_ratio=f"{data['summary_length']/data['original_length']:.1%}"
        )
        
        await processing_msg.delete()
        await self._safe_reply_text(update, summary_text, parse_mode='HTML')
    
    async def _rebuild_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /rebuild - перестроение базы знаний"""
        # Проверяем права администратора
        if not self._is_admin(update.message.from_user.id):
            await update.message.reply_text(self._get_template('errors', 'admin_only'))
            return
        
        # Отправляем сообщение о обработке
        processing_msg = await update.message.reply_text(self._get_template('messages', 'rebuilding'))
        
        data = self._make_api_request("POST", "/knowledge-base/rebuild")
        
        if not data:
            await processing_msg.delete()
            await update.message.reply_text(self._get_template('errors', 'rebuild_error'))
            return
        
        if data.get('status') == 'success':
            result_text = self._get_template('rebuild', 'success').format(
                message=self._escape_html(data.get('message', 'Успешно')),
                documents_count=data.get('documents_count', 0)
            )
        else:
            result_text = self._get_template('rebuild', 'error').format(
                message=self._escape_html(data.get('message', 'Неизвестная ошибка'))
            )
        
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
                await query.edit_message_text(self._get_template('errors', 'admin_only'))
                return
            
            # Показываем подтверждение
            keyboard = [
                [InlineKeyboardButton("✅ Да, перестроить", callback_data="confirm_rebuild")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_rebuild")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                self._get_template('rebuild', 'confirmation'),
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        elif query.data == "confirm_rebuild":
            await query.edit_message_text(self._get_template('messages', 'rebuilding'))
            
            data = self._make_api_request("POST", "/knowledge-base/rebuild")
            
            if data and data.get('status') == 'success':
                result_text = self._get_template('messages', 'rebuild_complete').format(
                    message=data.get('message', '')
                )
            else:
                result_text = self._get_template('messages', 'rebuild_failed')
            
            await query.edit_message_text(result_text)
        
        elif query.data == "cancel_rebuild":
            await query.edit_message_text(self._get_template('messages', 'rebuild_cancelled'))
        
        elif query.data == "show_stats":
            user = query.from_user
            
            # Получаем все диалоги пользователя
            dialogs = self.dialog_manager.get_user_dialogs(user.id)
            total_dialogs = len(dialogs)
            
            stats_text = f"""
<b>📊 Ваша статистика</b>

<b>Всего диалогов:</b> {total_dialogs}
<b>Активность с:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}
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
                self._get_template('errors', 'short_question'),
                reply_to_message_id=update.message.message_id
            )
            return
        
        # Получаем активный диалог
        dialog = self.dialog_manager.get_active_dialog(user.id)
        if not dialog:
            # Создаем новый диалог если активного нет
            dialog = self.dialog_manager.start_new_dialog(user.id, "Общий диалог")
        
        # Добавляем вопрос пользователя в диалог
        self.dialog_manager.add_message(user.id, 'user', question)
        
        # Отправляем сообщение о обработке
        processing_msg = await update.message.reply_text(self._get_template('messages', 'processing'))
        
        # Формируем запрос с контекстом
        request_text = f"Текущий вопрос: {question}"
        
        # Добавляем summary предыдущего диалога если есть
        if dialog.summary:
            request_text += f"\n\nКонтекст диалога: {dialog.summary}"
        
        # Отправляем вопрос в API
        data = self._make_api_request(
            "POST", 
            "/ask",
            json={
                "question": request_text
            }
        )
        
        if not data:
            await processing_msg.delete()
            await update.message.reply_text(
                self._get_template('errors', 'api_error'),
                reply_to_message_id=update.message.message_id
            )
            return
        
        # Добавляем ответ ассистента в диалог
        self.dialog_manager.add_message(user.id, 'assistant', data['answer'], data['tokens_used'])
        
        # Формируем секцию с источниками
        sources = data.get('sources', [])
        sources_list = ""
        if sources:
            source_items = []
            for i, source in enumerate(sources[:3], 1):
                relevance_percent = int((source.get('relevance_score', 0) or 0) * 100)
                source_name = self._escape_html(source.get('source', 'Неизвестный источник'))
                source_item = self._get_template('response', 'source_item').format(
                    index=i,
                    source=source_name,
                    relevance=relevance_percent
                )
                source_items.append(source_item)
            
            sources_list = self._get_template('response', 'sources_section').format(
                sources_list="\n".join(source_items)
            )
        
        # Форматируем ответ с HTML разметкой
        response_text = self._get_template('response', 'template').format(
            answer=self._escape_html(data['answer']),
            source_section=sources_list,
            tokens_used=data['tokens_used'],
            session_questions=len(dialog.messages),
            sources_count=len(sources)
        )
        
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
        logger.info(f"Настройки диалогов: {self.dialog_manager.max_messages} сообщений, {self.dialog_manager.max_dialogs} диалогов")
        logger.info(f"Загружено шаблонов: {len(self.templates)} категорий")
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
    print(f"Настройки диалогов: {bot.dialog_manager.max_messages} сообщений, {bot.dialog_manager.max_dialogs} диалогов")
    print(f"Шаблоны сообщений: {'загружены' if bot.templates else 'не загружены'}")
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