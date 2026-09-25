# 📚 Telegram Mini App — Библиотека аудиокниг

Приложение для прослушивания аудиокниг внутри Telegram: библиотека с обложками,
теги и поиск, плеер с перемоткой и автосохранением позиции. Аудиофайлы лежат в
**Yandex Object Storage**, а браузер качает их напрямую из хранилища по
подписанным ссылкам — backend в раздаче аудио не участвует и не падает под
нагрузкой.

---

## 🎯 Возможности

- ✅ **Запуск внутри Telegram** — Mini App без установки, открывается одной кнопкой
- ✅ **Структурированная библиотека** — книги с обложками, внутри каждой — главы
- ✅ **Поиск и фильтр по тегам** — по названию, тегам и чтецу
- ✅ **Полноценный плеер** — перемотка, скорость 0.75x–2x, автопродолжение
- ✅ **Отметки прогресса** — галочки на прослушанных главах, прогресс книги
- ✅ **Привязка к Telegram ID** — прогресс сохраняется для каждого пользователя
- ✅ **Раздача мимо сервера** — аудио идёт из Object Storage, backend только подписывает ссылки

---

## 📁 Структура проекта

```
audiobook-app/
├── bot/              # Telegram бот (регистрирует Mini App, обрабатывает /start)
├── backend/          # FastAPI API: каталог книг, подписанные ссылки, прогресс
├── frontend/         # Веб-интерфейс Mini App (HTML/CSS/JS)
└── AMVERA.md         # Инструкция по деплою на Amvera
```

---

## 🚀 Быстрый старт

### 1. Подготовьте бакет в Yandex Object Storage

Создайте бакет (например `librarium-audio`) с **приватным** доступом и положите
файлы в таком виде:

```
books/
├── Ересь Хоруса/
│   ├── cover.jpg
│   ├── text.txt
│   ├── 01 - Пролог.mp3
│   └── 02 - Глава первая.mp3
└── Пустая книга/
    └── 01.mp3
```

Где:
- `books/` — префикс, задаётся в `S3_BOOKS_PREFIX`
- имя папки — название книги и её id
- `cover.jpg` — обложка (ищется по имени, начинающемуся на `cover`)
- `text.txt` — теги, чтец и аннотация в формате ниже

### 2. Создайте сервисный аккаунт и ключ

1. Yandex Cloud → **IAM** → **Сервисные аккаунты** → создать `librarium-s3`
2. Выдать роль `storage.editor` на бакет
3. Открыть аккаунт → **Создать новый ключ** → **Создать статический ключ доступа**
4. Скопировать `Access Key ID` и `Secret` (секрет показывается один раз)

### 3. Настройте CORS в бакете

Без этого браузер не загрузит обложки и не даст перематывать аудио:

```json
[
  {
    "AllowedOrigins": ["https://your-frontend-url.com"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

`ExposeHeaders` с `Content-Range` обязателен — без него перемотка не работает.

### 4. Запустите backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

Создайте `.env` (скопируйте из `.env.example`):

```env
S3_BUCKET=librarium-audio
S3_ENDPOINT=https://storage.yandexcloud.net
S3_REGION=ru-central1
S3_ACCESS_KEY=ваш_access_key_id
S3_SECRET_KEY=ваш_секретный_ключ
S3_BOOKS_PREFIX=books/

TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
CORS_ORIGINS=http://localhost:5173
DATABASE_PATH=./audiobook.db

# Для локальной разработки без Telegram:
# DISABLE_TELEGRAM_AUTH=true
```

Запустите:

```bash
uvicorn app.main:app --reload --port 8000
```

Проверьте, что книги видны: `http://localhost:8000/api/debug/books`

### 5. Создайте Telegram бота

1. Напишите [@BotFather](https://t.me/BotFather)
2. Отправьте `/newbot`, следуйте инструкциям
3. Скопируйте токен бота
4. Отправьте `/newapp` → выберите бота → укажите название → загрузите иконку →
   **укажите URL фронтенда** (должен быть HTTPS)

### 6. Разверните фронтенд

**Вариант А: хостинг статики (Vercel / Netlify / Cloudflare Pages)**
- Загрузите папку `frontend/`
- В `frontend/config.js` укажите URL вашего backend:
  ```js
  const API_BASE_URL = "https://your-backend.com";
  ```
- Полученный HTTPS URL вставьте в настройки Mini App у @BotFather

**Вариант Б: локальная разработка через ngrok**
```bash
cd frontend
python -m http.server 5173
# В другом терминале:
ngrok http 5173
```
Скопируйте HTTPS URL из ngrok в @BotFather и в `backend/.env` → `CORS_ORIGINS`.

### 7. Запустите бота

```bash
cd bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Создайте `bot/.env`:

```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
WEBAPP_URL=https://your-frontend-url.com
```

Запустите:

```bash
python bot.py
```

### 8. Готово! 🎉

Откройте бота в Telegram → `/start` → нажмите кнопку «📚 Открыть библиотеку».

---

## 📝 Формат text.txt

```
#теги: Фэнтези, Эпик, Тёмное
#чтец: Иван Петров

Первая книга цикла. Мир на грани войны, древние силы пробуждаются.
```

- `#теги:` — список через запятую, используется для фильтра
- `#чтец:` — имя чтеца, показывается в карточке книги и **добавляется в теги**
- Всё остальное — текст аннотации

Строки с директивами можно ставить в любом порядке. Регистр не важен.

---

## 🛠️ Технологии

**Backend:**
- FastAPI (REST API)
- Yandex Object Storage через boto3 — листинг, чтение аннотаций, подпись ссылок
- Генерация presigned URL (SigV4) — аудио качает клиент напрямую, минуя сервер
- SQLite (хранение прогресса)
- Кэш листингов в памяти (`S3_CACHE_TTL`), чтобы не дёргать хранилище на каждый запрос

**Frontend:**
- Vanilla JS (без фреймворков)
- Нативный `<audio>` с поддержкой Range-запросов
- Адаптивный дизайн под тему Telegram
- Восстановление после истечения подписанной ссылки без потери позиции

**Bot:**
- python-telegram-bot (long polling)

---

## 🔌 API

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/books` | Список книг с обложками и тегами |
| GET | `/api/books/{id}/chapters` | Главы книги + подписанные `streamUrl` |
| GET | `/api/stream-url/{key}` | Свежая подписанная ссылка на главу |
| GET | `/api/stream/{key}` | Редирект 302 на подписанную ссылку (совместимость) |
| GET | `/api/cover/{key}` | Редирект 302 на ссылку обложки |
| POST | `/api/progress` | Сохранить позицию прослушивания |
| GET | `/api/progress/{user_id}` | Все позиции пользователя |
| POST | `/api/telegram/validate` | Проверка подписи initData |
| POST | `/api/cache/invalidate` | Сбросить кэш листингов после загрузки книг |
| GET | `/api/debug/books` | Диагностика: что найдено в каждой папке |
| GET | `/api/health` | Проверка живости |

---

## ⚙️ Переменные окружения

### backend

| Переменная | Обязательно | Описание |
|---|---|---|
| `S3_BUCKET` | да | Имя бакета |
| `S3_ACCESS_KEY` | да | Статический ключ доступа |
| `S3_SECRET_KEY` | да | Секрет ключа |
| `S3_ENDPOINT` | нет | По умолчанию `https://storage.yandexcloud.net` |
| `S3_REGION` | нет | По умолчанию `ru-central1` |
| `S3_BOOKS_PREFIX` | нет | Корневая папка библиотеки, по умолчанию `books/` |
| `S3_CACHE_TTL` | нет | Секунд кэша листингов, по умолчанию `300` |
| `S3_AUDIO_URL_TTL` | нет | Срок жизни ссылки на аудио, по умолчанию `86400` |
| `S3_COVER_URL_TTL` | нет | Срок жизни ссылки на обложку, по умолчанию `86400` |
| `CORS_ORIGINS` | да | Домены фронтенда через запятую |
| `DATABASE_PATH` | нет | По умолчанию `/data/audiobook.db` |
| `TELEGRAM_BOT_TOKEN` | да | Для проверки подписи initData |
| `DISABLE_TELEGRAM_AUTH` | нет | `true` только для локальной отладки |

### bot

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `WEBAPP_URL` | URL фронтенда |

---

## 🧪 Тесты

```bash
pip install -r backend/tests-requirements.txt
python3 backend/test_storage.py   # клиент хранилища на моке S3
python3 backend/test_api.py       # API-эндпоинты на моке S3
```

---

## ❗ Частые проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `/api/books` возвращает 500 | не заданы `S3_ACCESS_KEY` / `S3_SECRET_KEY` | проверьте переменные окружения |
| `Access Denied` | у сервисного аккаунта нет прав | выдайте роль `storage.editor` на бакет |
| Список книг пуст | префикс не совпадает | проверьте `S3_BOOKS_PREFIX` |
| Обложки не грузятся | CORS не настроен | добавьте домен фронтенда в CORS бакета |
| Плеер не перематывает | нет `ExposeHeaders` с `Content-Range` | поправьте CORS в бакете |
| Новые книги не видны | кэш листингов | `POST /api/cache/invalidate` |
| Аудио не играет | объект залит как `octet-stream` | код подставляет MIME при подписи, но проверьте CORS |
| Плеер остановился через сутки | истекла подписанная ссылка | обрабатывается автоматически; при желании увеличьте `S3_AUDIO_URL_TTL` |

---

## 🔐 Безопасность

- Бакет **приватный** — прямые ссылки без подписи не работают
- Ссылки подписываются на срок (`S3_AUDIO_URL_TTL`), утёкшая ссылка перестаёт действовать
- Секретный ключ хранится только в переменных окружения, никогда в git
- Прогресс привязан к Telegram ID, проверенному через подпись `initData`

---

## 📦 Деплой

Подробная инструкция по Amvera — в [AMVERA.md](AMVERA.md).
