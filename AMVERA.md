# Деплой на Amvera

Аудиофайлы хранятся в **Yandex Object Storage**, а не на Google Drive. Backend
их не раздаёт: он только подписывает ссылки, а браузер качает аудио напрямую
из хранилища. Поэтому узкое место — не контейнер backend, и он спокойно
обслуживает сотни одновременных слушателей.

Проект разворачивается как три отдельных приложения из одного репозитория.
Для каждого укажите корень репозитория как контекст сборки Docker и путь
к соответствующему Dockerfile ниже.

## 0. Что сделать в Yandex Cloud (один раз)

1. **Бакет.** Object Storage → создать бакет, например `librarium-audio`.
   Тип доступа — **приватный**, иначе книги скачает любой по прямой ссылке.
   Класс хранилища — «Стандартное».

2. **Сервисный аккаунт.** IAM → Сервисные аккаунты → создать `librarium-s3`,
   выдать роль `storage.editor` на бакет.

3. **Статический ключ.** Открыть сервисный аккаунт → «Создать новый ключ» →
   «Создать статический ключ доступа». Получите `Access Key ID` и `Secret`.
   **Секрет показывается один раз** — сохраните сразу.

4. **CORS.** Бакет → настройки → CORS. Без этого браузер не сможет
   ни загрузить обложку, ни перематывать аудио:

```json
[
  {
    "AllowedOrigins": ["https://librariumfrontend-eiolve.waw0.amvera.tech"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

`ExposeHeaders` с `Content-Range` и `Accept-Ranges` обязателен — именно из-за
его отсутствия чаще всего «плеер не перематывает».

5. **Структура файлов.** В бакете должны лежать книги в таком виде:

```text
books/Ересь Хоруса/cover.jpg
books/Ересь Хоруса/text.txt
books/Ересь Хоруса/01 - Пролог.mp3
books/Ересь Хоруса/02 - Глава первая.mp3
```

`books/` — префикс (задаётся через `S3_BOOKS_PREFIX`). Имя папки становится
id книги, имя файла — названием главы. Обложка ищется по имени, начинающемуся
на `cover`; если такой нет — берётся первое изображение. Теги и чтец читаются
из `text.txt` в прежнем формате:

```text
#теги: Фэнтези, Эпик
#чтец: Иван Петров

Текст аннотации.
```

Перенос с Google Drive удобнее всего делать через `rclone` — он сохранит
структуру папок как есть: `rclone copy gdrive:Книги yandex:librarium-audio/books/`.

## 1. Backend

- Dockerfile: `backend/Dockerfile`
- Публичный порт: `8000`
- Health-check: `/api/health`
- Подключите постоянный диск к `/data`, чтобы `audiobook.db` (прогресс
  прослушивания) не терялся при передеплое.

Переменные окружения:

```env
S3_BUCKET=librarium-audio
S3_ENDPOINT=https://storage.yandexcloud.net
S3_REGION=ru-central1
S3_ACCESS_KEY=ВАШ_ACCESS_KEY_ID
S3_SECRET_KEY=ВАШ_СЕКРЕТНЫЙ_КЛЮЧ
S3_BOOKS_PREFIX=books/
S3_CACHE_TTL=300
S3_AUDIO_URL_TTL=86400
S3_COVER_URL_TTL=86400
TELEGRAM_BOT_TOKEN=ТОКЕН_БОТА
CORS_ORIGINS=https://librariumfrontend-eiolve.waw0.amvera.tech
DATABASE_PATH=/data/audiobook.db
```

`S3_ACCESS_KEY` и `S3_SECRET_KEY` задавайте как **секреты** и не коммитьте
в репозиторий — от них зависит доступ к библиотеке.

`CORS_ORIGINS` можно указать несколько адресов через запятую.

`S3_CACHE_TTL` — сколько секунд backend держит в памяти список книг и глав,
чтобы не дёргать хранилище на каждый запрос. После загрузки новых книг
сбросьте кэш вручную:

```text
POST https://BACKEND_DOMAIN/api/cache/invalidate
```

## 2. Frontend

- Dockerfile: `frontend/Dockerfile`
- Публичный порт: `80`

Переменные окружения:

```env
API_BASE_URL=https://BACKEND_DOMAIN
```

При старте контейнера entrypoint-скрипт подставляет значение `API_BASE_URL`
вместо плейсхолдера `__API_BASE_URL__` в `config.js`. Указывайте адрес без
завершающего слэша.

После того как Amvera выдаст домен для frontend, обновите `CORS_ORIGINS`
в переменных backend и передеплойте backend.

## 3. Telegram-бот

- Dockerfile: `bot/Dockerfile`
- Публичный порт не требуется — бот работает через long polling.

Переменные окружения:

```env
TELEGRAM_BOT_TOKEN=ТОКЕН_БОТА
WEBAPP_URL=https://FRONTEND_DOMAIN
```

Запускайте только один экземпляр бота. Long polling не поддерживает несколько
параллельных реплик для одного токена — при двух и более копиях Telegram будет
присылать ошибку конфликта.

## 4. Настройка в Telegram

В @BotFather настройте URL Mini App — тот же адрес, что указан в `WEBAPP_URL`.
Затем откройте бота, отправьте `/start` и нажмите кнопку «Открыть библиотеку».

## 5. Проверка после деплоя

```text
https://BACKEND_DOMAIN/api/health      → {"status":"ok","storage":"librarium-audio"}
https://BACKEND_DOMAIN/api/books       → список книг из бакета
https://BACKEND_DOMAIN/api/debug/books → что нашлось в каждой папке
https://FRONTEND_DOMAIN                → открывается интерфейс библиотеки
```

Если `/api/books` возвращает 500 — смотрите текст ошибки в ответе. Частые
причины и что делать:

| Симптом | Причина | Решение |
|---|---|---|
| `S3_ACCESS_KEY не задан` | не проставлены переменные | добавьте их в секреты Amvera |
| `Access Denied` | у ключа нет прав на бакет | выдайте роль `storage.editor` |
| Список книг пуст | префикс не совпадает | проверьте `S3_BOOKS_PREFIX` |
| Плеер не перематывает | нет `ExposeHeaders` в CORS | поправьте CORS в бакете |
| Аудио не играет вовсе | объекты залиты как `octet-stream` | код подставляет MIME сам при подписи, но проверьте CORS |

## 6. Порядок деплоя

Рекомендуемая последовательность, чтобы не столкнуться с «яйцом и курицей»
по CORS:

1. Создайте бакет, сервисный аккаунт, ключ и настройте CORS (раздел 0).
2. Залейте одну тестовую книгу и проверьте её через `/api/debug/books`.
3. Разверните **backend**.
4. Разверните **frontend**, указав `API_BASE_URL` на домен backend.
5. Обновите `CORS_ORIGINS` в backend на реальный домен frontend и передеплойте.
6. Разверните **бота**, указав `WEBAPP_URL` на домен frontend.
7. Настройте Mini App в @BotFather.
8. Залейте остальные книги и вызовите `/api/cache/invalidate`.

## 7. Сводка переменных

```env
# backend
S3_BUCKET=librarium-audio
S3_ENDPOINT=https://storage.yandexcloud.net
S3_REGION=ru-central1
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BOOKS_PREFIX=books/
S3_CACHE_TTL=300
S3_AUDIO_URL_TTL=86400
S3_COVER_URL_TTL=86400
TELEGRAM_BOT_TOKEN=...
CORS_ORIGINS=https://FRONTEND_DOMAIN
DATABASE_PATH=/data/audiobook.db

# frontend
API_BASE_URL=https://BACKEND_DOMAIN

# bot
TELEGRAM_BOT_TOKEN=...
WEBAPP_URL=https://FRONTEND_DOMAIN
```

## 8. Экономика

Для 40 ГБ и примерно 1000 одновременных слушателей:

- Хранение: ~40 ГБ × ₽1.76/ГБ ≈ ₽70/мес.
- Исходящий трафик: ~₽1.5/ГБ. Это основная статья расходов при росте
  аудитории — следите за графиком трафика в консоли.

Так как аудио идёт напрямую из Object Storage, контейнер backend не тратит
трафик Amvera на раздачу аудио. Это и убирает прежние падения при стриминге.
