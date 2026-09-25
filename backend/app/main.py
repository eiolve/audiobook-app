import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from .progress_store import get_all_progress, init_db, save_progress  # noqa: E402
from .storage_client import (  # noqa: E402
    EMPTY_ANNOTATION,
    StorageClientError,
    audio_url,
    cover_url,
    find_annotation_file,
    find_cover_image,
    list_audio_files,
    list_book_folders,
    parse_annotation,
    read_annotation_file,
)
from .telegram_auth import get_telegram_user_id_from_init_data  # noqa: E402

app = FastAPI(title="Audiobook Player API")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", os.getenv("CORS_ORIGIN", "http://localhost:5173")
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _annotation_for(book_id: str) -> dict:
    """Аннотация книги, а при любой проблеме — пустая заглушка."""
    try:
        annotation_file = find_annotation_file(book_id)
        if annotation_file:
            return parse_annotation(read_annotation_file(annotation_file["id"]))
    except Exception:  # noqa: BLE001 — аннотация не критична, книга должна открыться
        pass
    return dict(EMPTY_ANNOTATION)


@app.get("/api/books")
def get_books():
    """
    Список аудиокниг — это «папки» внутри books/ в бакете.
    Для каждой книги дополнительно ищем обложку и text.txt с тегами.
    """
    try:
        folders = list_book_folders()
    except StorageClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    books = []
    for folder in folders:
        try:
            cover = find_cover_image(folder["id"])
        except Exception:
            cover = None

        parsed = _annotation_for(folder["id"])

        books.append(
            {
                "id": folder["id"],
                "title": folder["name"],
                "coverUrl": cover_url(cover["id"]) if cover else None,
                "tags": parsed["tags"],
                "narrator": parsed["narrator"],
            }
        )
    return books


@app.get("/api/books/{book_id}/chapters")
def get_chapters(book_id: str):
    """
    Список глав книги.

    Вместе с главами сразу отдаём подписанные ссылки на аудио: подпись считается
    локально, поэтому это не стоит ни одного лишнего запроса к хранилищу.
    Клиент далее качает файлы напрямую из Object Storage — backend в раздаче
    аудио не участвует и не падает под нагрузкой.
    """
    try:
        files = list_audio_files(book_id)
        cover = find_cover_image(book_id)
        parsed = _annotation_for(book_id)
    except StorageClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not files:
        raise HTTPException(
            status_code=404, detail="В этой папке не найдено аудиофайлов"
        )

    return {
        "coverUrl": cover_url(cover["id"]) if cover else None,
        "annotation": parsed["annotation"],
        "narrator": parsed["narrator"],
        "tags": parsed["tags"],
        "chapters": [
            {
                "id": f["id"],          # полный ключ объекта, стабилен между запросами
                "title": f["name"],
                "mimeType": f.get("mimeType", "audio/mpeg"),
                "sizeBytes": int(f.get("size", 0)) or None,
                "streamUrl": audio_url(f["id"]),
            }
            for f in files
        ],
    }


@app.get("/api/stream-url/{file_id:path}")
def get_stream_url(file_id: str):
    """
    Свежая подписанная ссылка на один аудиофайл.

    Нужна на случай, если глава слушается дольше срока жизни подписи:
    плеер ловит ошибку загрузки и перезапрашивает ссылку здесь.

    file_id принимаем как path-параметр, потому что ключ содержит слэши,
    кириллицу и пробелы — frontend кодирует его через encodeURIComponent.
    """
    try:
        return {"streamUrl": audio_url(file_id)}
    except StorageClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/stream/{file_id:path}")
async def stream_book(file_id: str):
    """
    Совместимость со старым фронтендом: отдаём 302 на подписанную ссылку.

    Аудио уходит клиенту напрямую из объекта в хранилище, а не через этот
    процесс, поэтому редирект дешевле проксирования и не создаёт узкого места.
    """
    from fastapi.responses import RedirectResponse

    try:
        return RedirectResponse(audio_url(file_id), status_code=302)
    except StorageClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/cover/{file_id:path}")
async def stream_cover(file_id: str):
    """Совместимость со старым фронтендом: редирект на подписанную ссылку обложки."""
    from fastapi.responses import RedirectResponse

    try:
        return RedirectResponse(cover_url(file_id), status_code=302)
    except StorageClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/cache/invalidate")
def invalidate_book_cache():
    """
    Сброс кэша листингов. Вызывать после загрузки новых книг в бакет,
    иначе библиотека обновится только по истечении S3_CACHE_TTL (по умолчанию 5 минут).
    """
    from .storage_client import invalidate_cache

    invalidate_cache()
    return {"ok": True}


@app.get("/api/debug/books")
def debug_books():
    """
    Диагностика: видно, какие файлы найдены в папке каждой книги,
    и что именно распозналось в text.txt.
    """
    try:
        folders = list_book_folders(bypass_cache=True)
    except StorageClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = []
    for folder in folders:
        info: dict = {
            "id": folder["id"],
            "title": folder["name"],
            "cover": None,
            "annotation_file": None,
            "raw_text": None,
            "parsed": None,
            "audio_count": None,
            "error": None,
        }
        try:
            cover = find_cover_image(folder["id"])
            info["cover"] = cover["name"] if cover else "NOT FOUND"

            audio = list_audio_files(folder["id"], bypass_cache=True)
            info["audio_count"] = len(audio)

            annotation_file = find_annotation_file(folder["id"])
            if annotation_file:
                info["annotation_file"] = annotation_file["name"]
                raw = read_annotation_file(annotation_file["id"])
                info["raw_text"] = raw[:500]
                info["parsed"] = parse_annotation(raw)
            else:
                info["annotation_file"] = "NOT FOUND"
        except Exception as exc:  # noqa: BLE001 — диагностика, показываем как есть
            info["error"] = str(exc)
        result.append(info)
    return result


class ProgressPayload(BaseModel):
    user_id: str
    file_id: str
    position_seconds: float


@app.post("/api/progress")
def post_progress(payload: ProgressPayload):
    """Сохранение позиции прослушивания (плеер вызывает периодически)."""
    save_progress(payload.user_id, payload.file_id, payload.position_seconds)
    return {"ok": True}


@app.get("/api/progress/{user_id}")
def get_progress_for_user(user_id: str):
    """Все сохранённые позиции пользователя (глава -> секунда)."""
    return get_all_progress(user_id)


class TelegramInitDataPayload(BaseModel):
    init_data: str


@app.post("/api/telegram/validate")
def validate_telegram_user(payload: TelegramInitDataPayload):
    """Проверяет подписанные данные Mini App и возвращает пользователя Telegram."""
    if os.getenv("DISABLE_TELEGRAM_AUTH", "false").lower() == "true":
        return {"user_id": "development_user"}

    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Telegram initData validation failed")
    return {"user_id": user_id}


@app.get("/api/health")
def health():
    """Проверка живости + сразу видно, настроено ли хранилище."""
    return {
        "status": "ok",
        "storage": os.getenv("S3_BUCKET", "not-configured"),
    }
