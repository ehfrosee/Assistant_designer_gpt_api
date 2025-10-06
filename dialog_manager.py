# -*- coding: utf-8 -*-
"""Менеджер диалогов для Telegram бота"""

import json
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

@dataclass
class DialogMessage:
    """Сообщение в диалоге"""
    role: str  # 'user' или 'assistant'
    content: str
    timestamp: str
    tokens_used: int = 0

@dataclass
class Dialog:
    """Диалог пользователя"""
    user_id: int
    dialog_id: str
    created_at: str
    topic: str = "Новая тема"
    messages: List[DialogMessage] = None
    summary: str = ""
    is_active: bool = True
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = []

class DialogManager:
    """Менеджер для работы с диалогами пользователей"""
    
    def __init__(self, storage_path: str = "dialogs", max_messages: int = 10, max_dialogs: int = 50):
        self.storage_path = storage_path
        self.max_messages = max_messages
        self.max_dialogs = max_dialogs
        self.active_dialogs: Dict[int, Dialog] = {}
        os.makedirs(storage_path, exist_ok=True)
    
    def _get_dialog_filename(self, user_id: int, dialog_id: str) -> str:
        """Получить имя файла для диалога"""
        return os.path.join(self.storage_path, f"{user_id}_{dialog_id}.json")
    
    def _generate_dialog_id(self) -> str:
        """Сгенерировать ID диалога"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def start_new_dialog(self, user_id: int, topic: str = "Новая тема") -> Dialog:
        """Начать новый диалог"""
        dialog_id = self._generate_dialog_id()
        dialog = Dialog(
            user_id=user_id,
            dialog_id=dialog_id,
            created_at=datetime.now().isoformat(),
            topic=topic
        )
        
        self.active_dialogs[user_id] = dialog
        self._save_dialog(dialog)
        
        # Очищаем старые диалоги если превышен лимит
        self._cleanup_old_dialogs(user_id)
        
        logging.info(f"Создан новый диалог для пользователя {user_id}: {dialog_id}")
        return dialog
    
    def get_active_dialog(self, user_id: int) -> Optional[Dialog]:
        """Получить активный диалог пользователя"""
        return self.active_dialogs.get(user_id)
    
    def add_message(self, user_id: int, role: str, content: str, tokens_used: int = 0) -> bool:
        """Добавить сообщение в активный диалог"""
        dialog = self.get_active_dialog(user_id)
        if not dialog:
            # Создаем новый диалог если активного нет
            dialog = self.start_new_dialog(user_id)
        
        message = DialogMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            tokens_used=tokens_used
        )
        
        dialog.messages.append(message)
        
        # Ограничиваем историю последними сообщениями согласно настройкам
        if len(dialog.messages) > self.max_messages:
            dialog.messages = dialog.messages[-self.max_messages:]
        
        self._save_dialog(dialog)
        return True
    
    def update_summary(self, user_id: int, summary: str) -> bool:
        """Обновить summary диалога"""
        dialog = self.get_active_dialog(user_id)
        if not dialog:
            return False
        
        dialog.summary = summary
        self._save_dialog(dialog)
        return True
    
    def _save_dialog(self, dialog: Dialog):
        """Сохранить диалог в файл"""
        filename = self._get_dialog_filename(dialog.user_id, dialog.dialog_id)
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                # Преобразуем dataclass в dict для сериализации
                dialog_dict = asdict(dialog)
                json.dump(dialog_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Ошибка сохранения диалога {filename}: {e}")
    
    def _cleanup_old_dialogs(self, user_id: int):
        """Очистить старые диалоги пользователя"""
        try:
            dialogs = self.get_user_dialogs(user_id)
            if len(dialogs) > self.max_dialogs:
                # Удаляем самые старые диалоги
                dialogs_to_delete = dialogs[self.max_dialogs:]
                for dialog in dialogs_to_delete:
                    filename = self._get_dialog_filename(user_id, dialog.dialog_id)
                    if os.path.exists(filename):
                        os.remove(filename)
                        logging.info(f"Удален старый диалог: {filename}")
        except Exception as e:
            logging.error(f"Ошибка очистки старых диалогов пользователя {user_id}: {e}")
    
    def load_dialog(self, user_id: int, dialog_id: str) -> Optional[Dialog]:
        """Загрузить диалог из файла"""
        filename = self._get_dialog_filename(user_id, dialog_id)
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                dialog = Dialog(
                    user_id=data['user_id'],
                    dialog_id=data['dialog_id'],
                    created_at=data['created_at'],
                    topic=data.get('topic', 'Новая тема'),
                    summary=data.get('summary', ''),
                    is_active=data.get('is_active', False)
                )
                # Восстанавливаем сообщения
                for msg_data in data.get('messages', []):
                    message = DialogMessage(
                        role=msg_data['role'],
                        content=msg_data['content'],
                        timestamp=msg_data['timestamp'],
                        tokens_used=msg_data.get('tokens_used', 0)
                    )
                    dialog.messages.append(message)
                
                return dialog
        except FileNotFoundError:
            return None
        except Exception as e:
            logging.error(f"Ошибка загрузки диалога {filename}: {e}")
            return None
    
    def get_user_dialogs(self, user_id: int) -> List[Dialog]:
        """Получить все диалоги пользователя"""
        dialogs = []
        try:
            for filename in os.listdir(self.storage_path):
                if filename.startswith(f"{user_id}_"):
                    dialog_id = filename.replace(f"{user_id}_", "").replace(".json", "")
                    dialog = self.load_dialog(user_id, dialog_id)
                    if dialog:
                        dialogs.append(dialog)
            
            # Сортируем по дате создания (новые сначала)
            dialogs.sort(key=lambda x: x.created_at, reverse=True)
            return dialogs
        except Exception as e:
            logging.error(f"Ошибка получения диалогов пользователя {user_id}: {e}")
            return []
    
    def export_dialog_text(self, dialog: Dialog) -> str:
        """Экспортировать диалог в текстовый формат"""
        lines = []
        lines.append(f"Диалог: {dialog.topic}")
        lines.append(f"Создан: {datetime.fromisoformat(dialog.created_at).strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"ID: {dialog.dialog_id}")
        lines.append(f"Сообщений: {len(dialog.messages)}")
        if dialog.summary:
            lines.append(f"Summary: {dialog.summary}")
        lines.append("=" * 50)
        
        for i, message in enumerate(dialog.messages, 1):
            role = "👤 Пользователь" if message.role == 'user' else "🤖 Ассистент"
            timestamp = datetime.fromisoformat(message.timestamp).strftime('%H:%M')
            lines.append(f"\n{i}. {role} [{timestamp}]:")
            lines.append(message.content)
            if message.tokens_used > 0:
                lines.append(f"[Использовано токенов: {message.tokens_used}]")
        
        lines.append("\n" + "=" * 50)
        lines.append(f"Всего сообщений: {len(dialog.messages)}")
        lines.append(f"Максимум сообщений в диалоге: {self.max_messages}")
        
        return "\n".join(lines)
    
    def export_dialog_json(self, dialog: Dialog) -> str:
        """Экспортировать диалог в JSON формат"""
        try:
            return json.dumps(asdict(dialog), ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Ошибка экспорта диалога в JSON: {e}")
            return ""