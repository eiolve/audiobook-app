"""
Telegram бот для запуска Mini App с аудиокнигами.

Регистрирует команду /start, которая отправляет кнопку открытия Web App.
Настройка Mini App URL производится через @BotFather командой /newapp.
"""
import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-frontend-url.com")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветствие и кнопку для открытия Mini App."""
    user = update.effective_user

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📚 Открыть библиотеку", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Это твоя личная библиотека аудиокниг.\n"
        "Нажми на кнопку ниже, чтобы начать слушать:",
        reply_markup=keyboard,
    )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN не задан в .env. "
            "Создайте бота через @BotFather и скопируйте токен в .env"
        )

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    logger.info("Бот запущен и ожидает команд...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
