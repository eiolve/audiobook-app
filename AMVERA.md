# Деплой на Amvera

Проект разворачивается как три отдельных приложения из одного репозитория. Для каждого укажите корень репозитория в качестве контекста сборки Docker и путь к соответствующему Dockerfile ниже.

## 1. Backend

- Dockerfile: `backend/Dockerfile`
- Публичный порт: `8000`
- Health-check: `/api/health`
- Подключите постоянный диск к `/data`, чтобы `audiobook.db` (прогресс прослушивания) не терялся при передеплое.

Переменные окружения:

```env
GOOGLE_DRIVE_FOLDER_ID=ID_КОРНЕВОЙ_ПАПКИ_БИБЛИОТЕКИ
GOOGLE_SERVICE_ACCOUNT_FILE=/run/secrets/google-service-account.json
TELEGRAM_BOT_TOKEN=ТОКЕН_БОТА
CORS_ORIGINS=https://FRONTEND_DOMAIN
DATABASE_PATH=/data/audiobook.db
```

JSON-ключ service account загрузите как защищённый (секретный) файл по пути `/run/secrets/google-service-account.json`. Корневую папку библиотеки на Google Drive нужно расшарить на email service account с ролью «Читатель».

`CORS_ORIGINS` можно указать несколько адресов через запятую, если понадобится.

## 2. Frontend

- Dockerfile: `frontend/Dockerfile`
- Публичный порт: `80`

Переменные окружения:

```env
API_BASE_URL=https://BACKEND_DOMAIN
```

При старте контейнера entrypoint-скрипт подставляет значение `API_BASE_URL` вместо плейсхолдера `__API_BASE_URL__` в `config.js`. Указывайте адрес без завершающего слэша.

После того как Amvera выдаст домен для frontend, обновите `CORS_ORIGINS` в переменных backend и передеплойте backend заново.

## 3. Telegram-бот

- Dockerfile: `bot/Dockerfile`
- Публичный порт не требуется — бот работает через long polling.

Переменные окружения:

```env
TELEGRAM_BOT_TOKEN=ТОКЕН_БОТА
WEBAPP_URL=https://FRONTEND_DOMAIN
```

Запускайте только один экземпляр бота. Long polling не поддерживает несколько параллельных реплик для одного токена — при двух и более копиях Telegram будет присылать ошибку конфликта.

## 4. Настройка в Telegram

В @BotFather настройте URL Mini App — тот же адрес, что указан в `WEBAPP_URL`. Затем откройте бота, отправьте `/start` и нажмите кнопку «Открыть библиотеку».

## 5. Проверка после деплоя

```text
https://BACKEND_DOMAIN/api/health      → {"status":"ok"}
https://BACKEND_DOMAIN/api/books       → список папок-книг из Google Drive
https://FRONTEND_DOMAIN                → открывается интерфейс библиотеки
```

Если `/api/books` возвращает 500 — проверьте `GOOGLE_DRIVE_FOLDER_ID` (это должен быть только ID, не весь URL) и доступ service account к папке.

## 6. Порядок деплоя

Рекомендуемая последовательность, чтобы не столкнуться с "яйцом и курицей" по CORS:

1. Разверните **backend** (можно с временным `CORS_ORIGINS`, например `https://localhost`).
2. Разверните **frontend**, указав `API_BASE_URL` на уже полученный домен backend.
3. Обновите `CORS_ORIGINS` в backend на реальный домен frontend и передеплойте backend.
4. Разверните **бота**, указав `WEBAPP_URL` на домен frontend.
5. Настройте Mini App в @BotFather.

## 7. Структура переменных — сводка

```env
# backend
GOOGLE_SERVICE_ACCOUNT_FILE=/run/secrets/google-service-account.json
GOOGLE_DRIVE_FOLDER_ID=DRIVE_FOLDER_ID
TELEGRAM_BOT_TOKEN=BOT_TOKEN
CORS_ORIGINS=https://FRONTEND_DOMAIN
DATABASE_PATH=/data/audiobook.db
```

```env
# frontend
API_BASE_URL=https://BACKEND_DOMAIN
```

```env
# bot
TELEGRAM_BOT_TOKEN=BOT_TOKEN
WEBAPP_URL=https://FRONTEND_DOMAIN
```
