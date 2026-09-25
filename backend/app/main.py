import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from .drive_client import (  # noqa: E402
    DriveClientError,
    find_annotation_file,
    find_cover_image,
    list_audio_files,
    list_book_folders,
    parse_annotation,
    read_annotation_file,
)
from .progress_store import get_all_progress, init_db, save_progress  # noqa: E402
from .streaming import stream_drive_file  # noqa: E402
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


def _get_root_folder_id() -> str:
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise HTTPException(status_code=500, detail="GOOGLE_DRIVE_FOLDER_ID не задан в .env")
    return folder_id


@app.get("/api/books")
def get_books():
    """
    Список аудиокниг — это папки внутри корневой папки библиотеки на Google Drive.
    Для каждой книги дополнительно ищем обложку и text.txt с тегами.
    """
    root_folder_id = _get_root_folder_id()
    try:
        folders = list_book_folders(root_folder_id)
    except DriveClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    books = []
    for folder in folders:
        try:
            cover = find_cover_image(folder["id"])
        except Exception:
            cover = None

        try:
            annotation_file = find_annotation_file(folder["id"])
            parsed = (
                parse_annotation(read_annotation_file(annotation_file["id"]))
                if annotation_file
                else {"tags": [], "narrator": "", "annotation": ""}
            )
        except Exception:
            parsed = {"tags": [], "narrator": "", "annotation": ""}

        books.append(
            {
                "id": folder["id"],
                "title": folder["name"],
                "coverFileId": cover["id"] if cover else None,
                "tags": parsed["tags"],
                "narrator": parsed["narrator"],
            }
        )
    return books


@app.get("/api/debug/books")
def debug_books():
    """Диагностический endpoint — показывает теги и аннотацию для каждой книги."""
    root_folder_id = _get_root_folder_id()
    try:
        folders = list_book_folders(root_folder_id)
    except DriveClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = []
    for folder in folders:
        info: dict = {"id": folder["id"], "title": folder["name"], "annotation_file": None, "raw_text": None, "parsed": None, "error": None}
        try:
            annotation_file = find_annotation_file(folder["id"])
            if annotation_file:
                info["annotation_file"] = annotation_file["name"]
                raw = read_annotation_file(annotation_file["id"])
                info["raw_text"] = raw[:500]
                info["parsed"] = parse_annotation(raw)
            else:
                info["annotation_file"] = "NOT FOUND"
        except Exception as exc:
            info["error"] = str(exc)
        result.append(info)
    return result


@app.get("/api/books/{book_id}/chapters")
def get_chapters(book_id: str):
    """Список глав (аудиофайлов) внутри папки книги, отсортированных по имени."""
    try:
        files = list_audio_files(book_id)
        cover = find_cover_image(book_id)
        annotation_file = find_annotation_file(book_id)
        parsed = (
            parse_annotation(read_annotation_file(annotation_file["id"]))
            if annotation_file
            else {"tags": [], "narrator": "", "annotation": ""}
        )
    except DriveClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not files:
        raise HTTPException(status_code=404, detail="В этой папке не найдено аудиофайлов")

    return {
        "coverFileId": cover["id"] if cover else None,
        "annotation": parsed["annotation"],
        "narrator": parsed["narrator"],
        "tags": parsed["tags"],
        "chapters": [
            {
                "id": f["id"],
                "title": f["name"],
                "mimeType": f.get("mimeType", "audio/mpeg"),
                "sizeBytes": int(f.get("size", 0)) if f.get("size") else None,
            }
            for f in files
        ],
    }


@app.get("/api/stream/{file_id}")
async def stream_book(file_id: str, request: Request):
    """Стриминг аудиофайла с поддержкой перемотки (Range-запросы)."""
    return await stream_drive_file(file_id, request, default_mime="audio/mpeg")


@app.get("/api/cover/{file_id}")
async def stream_cover(file_id: str, request: Request):
    """Отдаёт изображение обложки книги."""
    return await stream_drive_file(file_id, request, default_mime="image/jpeg")


class ProgressPayload(BaseModel):
    user_id: str
    file_id: str
    position_seconds: float


@app.post("/api/progress")
def post_progress(payload: ProgressPayload):
    """Сохранение позиции прослушивания (вызывается плеером периодически)."""
    save_progress(payload.user_id, payload.file_id, payload.position_seconds)
    return {"ok": True}


@app.get("/api/progress/{user_id}")
def get_progress_for_user(user_id: str):
    """Все сохранённые позиции прослушивания пользователя (глава -> секунда)."""
    return get_all_progress(user_id)


class TelegramInitDataPayload(BaseModel):
    init_data: str


@app.post("/api/telegram/validate")
def validate_telegram_user(payload: TelegramInitDataPayload):
    """Validates signed Mini App data and returns the authenticated Telegram user."""
    if os.getenv("DISABLE_TELEGRAM_AUTH", "false").lower() == "true":
        return {"user_id": "development_user"}

    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Telegram initData validation failed")
    return {"user_id": user_id}


@app.get("/api/health")
def health():
    return {"status": "ok"}
