"""
Клиент для работы с Google Drive API.

Используется service account — отдельная "техническая" учётная запись Google,
которой вы даёте доступ на чтение к папке с аудиокнигами. Так не нужно
хранить личный OAuth-токен пользователя и переживать за его протухание.

Настройка описана в README.md.
"""
import os
from functools import lru_cache

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class DriveClientError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_drive_service():
    """Создаёт (и кэширует) клиент Google Drive API."""
    key_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    if not os.path.exists(key_path):
        raise DriveClientError(
            f"Не найден файл service account: {key_path}. "
            "Смотрите README.md, раздел 'Настройка Google Drive'."
        )
    credentials = service_account.Credentials.from_service_account_file(
        key_path, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


AUDIO_QUERY_FRAGMENT = (
    "(mimeType contains 'audio/' or name contains '.mp3' or name contains '.m4a' or name contains '.m4b')"
)

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".wav", ".flac", ".opus")

# Расширения, которые считаем обложкой книги
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _list_children(folder_id: str, extra_query: str, fields: str) -> list[dict]:
    """Общая пагинация по содержимому папки с произвольным доп.условием запроса."""
    service = get_drive_service()
    query = f"'{folder_id}' in parents and trashed = false and {extra_query}"
    items: list[dict] = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields=f"nextPageToken, files({fields})",
                pageToken=page_token,
                pageSize=200,
                orderBy="name",
            )
            .execute()
        )
        items.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return items


def list_book_folders(root_folder_id: str) -> list[dict]:
    """
    Возвращает список папок-книг внутри корневой папки библиотеки.

    Каждый элемент: id, name.
    """
    return _list_children(
        root_folder_id,
        "mimeType = 'application/vnd.google-apps.folder'",
        "id, name",
    )


def list_audio_files(folder_id: str) -> list[dict]:
    """
    Возвращает список аудиофайлов (глав) внутри папки книги, отсортированных по имени.

    Каждый элемент содержит: id, name, mimeType, size (в байтах, строкой).
    """
    files = _list_children(
        folder_id,
        AUDIO_QUERY_FRAGMENT,
        "id, name, mimeType, size, description",
    )
    # Keep only real audio files. Drive metadata can be inconsistent, so reject
    # known non-audio files even when their MIME type is incorrect.
    non_audio_names = ("text.txt", "cover.jpg", "cover.jpeg", "cover.png", "cover.webp")
    return [
        file
        for file in files
        if (
            file.get("name", "").strip().lower() not in non_audio_names
            and (
                file.get("mimeType", "").lower().startswith("audio/")
                or file.get("name", "").lower().endswith(AUDIO_EXTENSIONS)
            )
        )
    ]


def find_cover_image(folder_id: str) -> dict | None:
    """
    Ищет файл обложки внутри папки книги.

    Сначала ищет файл с именем, начинающимся на "cover" (без учёта регистра).
    Если не находит — берёт первое попавшееся изображение в папке.
    Возвращает None, если изображений нет вовсе.
    """
    images = _list_children(
        folder_id,
        "mimeType contains 'image/'",
        "id, name, mimeType",
    )
    if not images:
        return None

    for image in images:
        name_lower = image["name"].lower()
        if name_lower.startswith("cover") and name_lower.endswith(COVER_EXTENSIONS):
            return image

    return images[0]


def find_annotation_file(folder_id: str) -> dict | None:
    """Finds text.txt in a book folder, ignoring case and surrounding spaces."""
    files = _list_children(
        folder_id,
        "mimeType != 'application/vnd.google-apps.folder'",
        "id, name, mimeType, size",
    )
    for file in files:
        if file.get("name", "").strip().lower() == "text.txt":
            return file
    return None


def read_annotation_file(file_id: str) -> str:
    """Downloads the UTF-8 book annotation from Google Drive."""
    content = get_drive_service().files().get_media(fileId=file_id).execute()
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, bytes):
        for encoding in ("utf-8-sig", "cp1251", "utf-16"):
            try:
                return content.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
    return str(content).strip()


def parse_annotation(raw: str) -> dict:
    """
    Parses text.txt content and extracts tags, narrator, and annotation body.

    Supported format (order of lines does not matter, they must come before
    the first blank line):

        #теги: Тег1, Тег2, Тег3
        #чтец: Имя Чтеца

        Текст аннотации начинается здесь.

    Returns a dict with keys: tags (list[str]), narrator (str), annotation (str).
    The narrator is also appended to the tags list for filtering.
    """
    lines = raw.splitlines()
    tags: list[str] = []
    narrator: str = ""
    body_lines: list[str] = []
    header_done = False

    for line in lines:
        stripped = line.strip()

        if not header_done:
            low = stripped.lower()
            if low.startswith("#теги:"):
                raw_tags = stripped[len("#теги:"):].strip()
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                continue
            if low.startswith("#чтец:"):
                narrator = stripped[len("#чтец:"):].strip()
                continue
            # First non-meta line ends the header block
            if stripped != "":
                header_done = True
                body_lines.append(line)
        else:
            body_lines.append(line)

    # Narrator is also a filterable tag
    if narrator and narrator not in tags:
        tags.append(narrator)

    return {
        "tags": tags,
        "narrator": narrator,
        "annotation": "\n".join(body_lines).strip(),
    }


def get_file_metadata(file_id: str) -> dict:
    """Возвращает метаданные одного файла (имя, размер, mime-тип)."""
    service = get_drive_service()
    return (
        service.files()
        .get(fileId=file_id, fields="id, name, mimeType, size")
        .execute()
    )


def get_credentials_token() -> str:
    """
    Возвращает свежий access-токен service account.

    Нужен, чтобы делать прямые HTTP-запросы к Drive (для стриминга с Range),
    а не через google-api-python-client, который Range не поддерживает.
    """
    key_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    credentials = service_account.Credentials.from_service_account_file(
        key_path, scopes=SCOPES
    )
    from google.auth.transport.requests import Request

    credentials.refresh(Request())
    return credentials.token
