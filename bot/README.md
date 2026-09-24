# Telegram бот для запуска Mini App

Этот простой бот отправляет inline-кнопку, которая открывает ваш Mini App с аудиокнигами.

## Настройка

### 1. Создайте бота через @BotFather

1. Напишите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям (имя, username)
4. Скопируйте токен — он понадобится ниже

### 2. Зарегистрируйте Mini App

1. Снова напишите @BotFather
2. Отправьте `/newapp`
3. Выберите вашего бота
4. Укажите название Mini App (например, "Аудиокниги")
5. Загрузите иконку 640×360 (любую картинку)
6. **Укажите URL вашего фронтенда** (должен быть HTTPS — для разработки можно использовать ngrok или похожий туннель)

### 3. Заполните `.env`

Скопируйте `.env.example` в `.env` и заполните:
```bash
cp .env.example .env
nano .env
```

```
TELEGRAM_BOT_TOKEN=1234567890:ABC-DEF...     # токен от BotFather
WEBAPP_URL=https://your-domain.com           # URL вашего фронтенда
```

### 4. Установите зависимости и запустите

```bash
python -m venv venv
source venv/bin/activate   # на Windows: venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

Бот теперь слушает команду `/start` и открывает ваш Mini App.

## Для разработки (локально)

Telegram Mini Apps требуют HTTPS. Для локальной разработки:

1. Используйте [ngrok](https://ngrok.com/):
   ```bash
   ngrok http 5173
   ```
   Скопируйте HTTPS URL (например, `https://abc123.ngrok-free.app`) в `WEBAPP_URL` бота и в @BotFather при создании Mini App.

2. Или разверните фронтенд на бесплатном хостинге (Vercel, Netlify, Cloudflare Pages) и укажите его URL.
