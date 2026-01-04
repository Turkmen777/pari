# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Получаем значения из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен из .env файла
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1003663534213"))
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "8444800411").split(",")]
MIN_AMOUNT = float(os.getenv("MIN_AMOUNT", 50))

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен! Создайте файл .env или установите переменные окружения")