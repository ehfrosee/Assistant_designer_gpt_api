#!/usr/bin/env python3
"""Скрипт запуска Telegram бота"""

import os
import sys
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Проверка обязательных переменных
if not os.getenv('TELEGRAM_BOT_TOKEN'):
    print("Ошибка: TELEGRAM_BOT_TOKEN не установлен в .env файле")
    sys.exit(1)

if not os.getenv('OPENAI_API_KEY'):
    print("Ошибка: OPENAI_API_KEY не установлен в .env файле")
    sys.exit(1)

# Запуск бота
from telegram_bot import main

if __name__ == '__main__':
    main()