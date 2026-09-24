"""
Валидация initData от Telegram Mini Apps.

Telegram передаёт данные пользователя в window.Telegram.WebApp.initData (URL-encoded строка).
Мы должны проверить её подпись (hash), чтобы убедиться, что данные не подделаны.

Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import os
from urllib.parse import parse_qsl


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет подпись initData и возвращает распарсенные данные, если подпись валидна.
    Возвращает None, если подпись неверна (данные подделаны).

    init_data — строка вида "query_id=...&user=...&auth_date=...&hash=..."
    bot_token — токен вашего Telegram бота
    """
    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Собираем data_check_string: ключи в алфавитном порядке, соединённые \n
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # Вычисляем ключ для HMAC: HMAC-SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256,
        ).digest()

        # Вычисляем hash: HMAC-SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if calculated_hash != received_hash:
            return None

        return parsed
    except Exception:
        return None


def get_telegram_user_id_from_init_data(init_data: str) -> str | None:
    """
    Извлекает Telegram user ID из валидного initData.
    Возвращает строку вида "telegram_123456789" или None, если данные невалидны.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        # Для локальной разработки без бота можно отключить валидацию
        return None

    validated = validate_telegram_init_data(init_data, bot_token)
    if not validated:
        return None

    # Поле "user" содержит JSON-строку с данными пользователя
    import json

    user_json = validated.get("user")
    if not user_json:
        return None

    try:
        user = json.loads(user_json)
        user_id = user.get("id")
        return f"telegram_{user_id}" if user_id else None
    except Exception:
        return None
