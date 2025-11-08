import os
from datetime import time

# Токен бота
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Настройки базы данных
DATABASE_NAME = "sleep_tracker.db"

# Время для автоматического создания записей (23:00)
AUTO_CREATE_TIME = time(23, 0, 0)

# Настройка логирования
LOGGING_LEVEL = "WARNING"  # Уменьшаем спам в консоли