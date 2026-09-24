# 📚 Telegram Mini App — Аудиокниги с Google Drive

Полноценное приложение для прослушивания аудиокниг внутри Telegram, с автосохранением прогресса и структурой "книга → главы". Аудиофайлы и обложки хранятся на Google Drive, стриминг через FastAPI backend.

---

## 🎯 Возможности

- ✅ **Запуск внутри Telegram** — Mini App без установки, открывается одной кнопкой
- ✅ **Структурированная библиотека** — книги с обложками, внутри каждой — главы
- ✅ **Полноценный плеер** — перемотка, скорость 0.75x–2x, автосохранение позиции
- ✅ **Автопродолжение** — при окончании главы автоматически включается следующая
- ✅ **Привязка к Telegram ID** — прогресс прослушивания сохраняется для каждого пользователя
- ✅ **Адаптивный дизайн** — автоматически подстраивается под тему Telegram (светлая/тёмная)

---

## 📁 Структура проекта

```
audiobook-app/
├── bot/              # Telegram бот (регистрирует Mini App, обрабатывает /start)
├── backend/          # FastAPI API: каталог книг, стриминг, прогресс
├── frontend/         # Веб-интерфейс Mini App (HTML/CSS/JS)
└── README.md
```

---

## 🚀 Быстрый старт

### 1. Подготовьте Google Drive

Создайте структуру папок:
```
Моя библиотека/
├── Война и мир/
│   ├── cover.jpg
│   ├── 01 - Том первый.mp3
│   ├── 02 - Том второй.mp3
│   └── ...
├── Мастер и Маргарита/
│   ├── cover.png
│   ├── 01 - Часть первая.mp3
│   └── ...
```

**Настройка доступа (service account):**
1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте проект (или используйте существующий)
3. Включите **Google Drive API** ([ссылка](https://console.cloud.google.com/apis/library/drive.googleapis.com))
4. Создайте **Service Account**:
   - IAM & Admin → Service Accounts → Create Service Account
   - Скачайте JSON-ключ
   - Скопируйте email service account (вида `...@...iam.gserviceaccount.com`)
5. **Откройте корневую папку библиотеки** на Google Drive → ПКМ → "Поделиться" → вставьте email service account, дайте роль "Читатель"
6. Скопируйте **ID папки** из URL (`drive.google.com/drive/folders/ВОТ_ЭТО`)

### 2. Настройте backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

Создайте `.env` (скопируйте из `.env.example`):
```env
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
GOOGLE_DRIVE_FOLDER_ID=1E1e_xtzarIoGkWmPg5ubzlvQgV6A78WG
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
CORS_ORIGIN=https://your-frontend-url.com
# Для локальной разработки без Telegram:
# DISABLE_TELEGRAM_AUTH=true
```

Положите скачанный JSON-ключ service account в `backend/service_account.json`.

Запустите:
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Создайте Telegram бота

1. Напишите [@BotFather](https://t.me/BotFather)
2. Отправьте `/newbot`, следуйте инструкциям
3. Скопируйте токен бота
4. Отправьте `/newapp` → выберите бота → укажите название → загрузите иконку → **укажите URL фронтенда** (должен быть HTTPS)

### 4. Разверните фронтенд

**Вариант А: GitHub Pages / Vercel / Netlify** (рекомендуется)
- Загрузите папку `frontend/` на хостинг
- В `frontend/config.js` укажите URL вашего backend:
  ```js
  const API_BASE_URL = "https://your-backend.com";
  ```
- Скопируйте полученный HTTPS URL фронтенда в настройки Mini App у @BotFather

**Вариант Б: локальная разработка через ngrok**
```bash
cd frontend
python -m http.server 5173
# В другом терминале:
ngrok http 5173
```
Скопируйте HTTPS URL из ngrok в @BotFather и в `backend/.env` → `CORS_ORIGIN`.

### 5. Запустите бота

```bash
cd bot
python -m venv venv
venv\Scripts\activate
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

### 6. Готово! 🎉

Откройте бота в Telegram → `/start` → нажмите кнопку "📚 Открыть библиотеку".

---

## 🛠️ Технологии

**Backend:**
- FastAPI (REST API)
- Google Drive API (стриминг с Range-запросами)
- SQLite (хранение прогресса)
- httpx (прокси аудио/обложек)

**Frontend:**
- Vanilla JS (без фреймворков)
- Telegram WebApp SDK (интеграция с темой, haptic feedback)
- HTML5 `<audio>` (плеер с нативной поддержкой перемотки)

**Bot:**
- python-telegram-bot (inline-кнопка для запуска Mini App)

---

## 📖 Использование

1. Откройте бота в Telegram → `/start`
2. Нажмите "📚 Открыть библиотеку"
3. Выберите книгу из списка (с обложкой)
4. Выберите главу
5. Плеер появится внизу — управление перемоткой, скоростью
6. Прогресс сохраняется автоматически каждые 5 секунд
7. При следующем запуске продолжите с места остановки

**Порядок глав:** файлы сортируются по имени, поэтому называйте их с числовым префиксом:
```
01 - Глава первая.mp3
02 - Глава вторая.mp3
...
10 - Глава десятая.mp3
```

**Обложки:** файл с именем `cover.*` (jpg/png/webp) внутри папки книги. Если не найдётся — берётся первое попавшееся изображение в папке.

---

## 🔒 Безопасность

- **initData валидация**: backend проверяет подпись данных от Telegram (HMAC-SHA256), чтобы исключить подделку user ID
- **Service account вместо OAuth**: не требует личного токена пользователя, только доступ на чтение к одной папке Drive
- **CORS**: ограничен только вашим фронтендом + Telegram origins

---

## 🐛 Troubleshooting

**Backend падает с `500` при `/api/books`:**
- Проверьте, что `GOOGLE_DRIVE_FOLDER_ID` — это только ID, не весь URL
- Убедитесь, что email service account добавлен в "Поделиться" для корневой папки на Drive

**Фронтенд показывает "Failed to fetch":**
- Откройте консоль браузера (F12) — там будет CORS-ошибка или `net::ERR_CONNECTION_REFUSED`
- Проверьте, что backend запущен и `API_BASE_URL` в `config.js` правильный

**Прогресс не сохраняется:**
- Проверьте, что `TELEGRAM_BOT_TOKEN` в `backend/.env` совпадает с токеном бота
- Для локальной разработки без Telegram добавьте `DISABLE_TELEGRAM_AUTH=true` в `backend/.env`

**Mini App не открывается в Telegram:**
- URL фронтенда должен быть HTTPS (локально используйте ngrok)
- Проверьте, что URL в @BotFather и в `bot/.env` совпадают

---

## 📦 Деплой на VPS (production)

1. Backend: запустите через systemd или supervisor с `uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. Frontend: разверните статику через nginx
3. Bot: запустите через systemd как отдельный сервис
4. Используйте reverse proxy (nginx/caddy) с автоматическими SSL-сертификатами от Let's Encrypt

Пример nginx для backend:
```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📄 Лицензия

MIT — делайте что хотите, но автор не несёт ответственности за ваше использование.

---

Если что-то не работает — пишите issue, разберёмся.
