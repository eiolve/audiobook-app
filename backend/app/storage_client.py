"""
Клиент для работы с Yandex Object Storage (S3-совместимое API).

Заменяет прежний drive_client: раньше «папка книги» была объектом Google Drive
со своим ID, теперь папки как таковой нет вообще — объектное хранилище плоское,
а «папка» это просто общий префикс ключей.

    books/Название книги/cover.jpg
    books/Название книги/text.txt
    books/Название книги/01 - Глава первая.mp3

Поэтому:
    id книги  = имя папки  (последний сегмент префикса, кириллица допустима)
    id главы  = полный ключ объекта (уникален в пределах бакета)

Ключи содержат кириллицу и пробелы, поэтому в URL они передаются
URL-encoded (frontend делает encodeURIComponent, FastAPI декодирует сам).
"""

import os
import time
from functools import lru_cache
from typing import Any, Callable

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

# ---------- Константы ----------

DEFAULT_ENDPOINT = "https://storage.yandexcloud.net"
DEFAULT_REGION = "ru-central1"

# Расширения, которые считаем аудио
AUDIO_EXTENSIONS = (
    ".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".wav", ".flac", ".opus",
)

# Расширения, которые считаем обложкой
COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# Имя файла с аннотацией и тегами
ANNOTATION_FILENAME = "text.txt"

# MIME-типы. Нужны потому, что при заливке через rclone объекты легко
# получают application/octet-stream, а браузерный <audio> такой файл играть
# откажется. Мы принудительно подставляем правильный Content-Type прямо
# в подписанную ссылку (response-content-type), не перезаливая объекты.
AUDIO_MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".m4b": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}

COVER_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class StorageClientError(RuntimeError):
    """Ошибка обращения к хранилищу — отдаётся клиенту как 500 с понятным текстом."""


# ---------- Настройки ----------


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise StorageClientError(f"{name} не задан в переменных окружения")
    return value


def get_bucket() -> str:
    return _env("S3_BUCKET")


def get_books_prefix() -> str:
    """Префикс корневой папки библиотеки, всегда с завершающим слэшем."""
    prefix = os.getenv("S3_BOOKS_PREFIX", "books/")
    return prefix if prefix.endswith("/") else prefix + "/"


@lru_cache(maxsize=1)
def get_s3_client():
    """
    Создаёт (и кэширует) клиент S3.

    Подпись s3v4 — то, что понимает Yandex Object Storage.
    Клиент потокобезопасен, поэтому один экземпляр на процесс.
    """
    endpoint = os.getenv("S3_ENDPOINT", DEFAULT_ENDPOINT)
    region = os.getenv("S3_REGION", DEFAULT_REGION)
    access_key = _env("S3_ACCESS_KEY")
    secret_key = _env("S3_SECRET_KEY")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )


# ---------- Кэш листингов ----------
# Листинг бакета — сетевой запрос к Yandex. При тысяче слушателей, открывающих
# библиотеку, незачем дёргать его на каждый запрос: состав книг меняется редко.
# Держим результат в памяти процесса на несколько минут.

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = float(os.getenv("S3_CACHE_TTL", "300"))


def _cached(cache_key: str, producer: Callable[[], Any], bypass: bool = False) -> Any:
    now = time.time()
    if not bypass:
        hit = _CACHE.get(cache_key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    value = producer()
    _CACHE[cache_key] = (now, value)
    return value


def invalidate_cache() -> None:
    """Сбросить кэш листингов — вызывается после загрузки новых книг."""
    _CACHE.clear()


# ---------- Утилиты путей ----------


def book_prefix(book_id: str) -> str:
    """Префикс всех объектов книги: books/<имя папки>/"""
    return f"{get_books_prefix()}{book_id}/"


def key_from_book(book_id: str, filename: str) -> str:
    return f"{book_prefix(book_id)}{filename}"


def filename_of(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def extension_of(key: str) -> str:
    name = filename_of(key).lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def is_audio_key(key: str) -> bool:
    return extension_of(key) in AUDIO_EXTENSIONS


def is_cover_key(key: str) -> bool:
    return extension_of(key) in COVER_EXTENSIONS


def guess_audio_mime(key: str) -> str:
    return AUDIO_MIME_BY_EXT.get(extension_of(key), "audio/mpeg")


def guess_cover_mime(key: str) -> str:
    return COVER_MIME_BY_EXT.get(extension_of(key), "image/jpeg")


# ---------- Листинг ----------


def _list_objects(prefix: str, delimiter: str | None = "/") -> dict:
    """Одна страница list_objects_v2 (с пагинацией внутри)."""
    client = get_s3_client()
    bucket = get_bucket()
    contents: list[dict] = []
    common_prefixes: list[str] = []

    kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
    if delimiter:
        kwargs["Delimiter"] = delimiter

    while True:
        try:
            response = client.list_objects_v2(**kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise StorageClientError(f"Не удалось получить список объектов: {exc}") from exc

        contents.extend(response.get("Contents", []))
        common_prefixes.extend(p.get("Prefix", "") for p in response.get("CommonPrefixes", []))

        if not response.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = response["NextContinuationToken"]

    return {"contents": contents, "prefixes": common_prefixes}


def list_book_folders(bypass_cache: bool = False) -> list[dict]:
    """
    Список книг — это «папки» внутри books/.

    Бакет плоский, поэтому «папки» получаем через Delimiter='/':
    S3 вернёт их в CommonPrefixes, одним запросом на всю библиотеку.
    """
    prefix = get_books_prefix()

    def producer() -> list[dict]:
        data = _list_objects(prefix, delimiter="/")
        books = []
        for common_prefix in data["prefixes"]:
            name = common_prefix[len(prefix):].rstrip("/")
            if not name:
                continue
            books.append({"id": name, "name": name})
        books.sort(key=lambda b: b["name"].lower())
        return books

    return _cached(f"books:{prefix}", producer, bypass=bypass_cache)


def list_audio_files(book_id: str, bypass_cache: bool = False) -> list[dict]:
    """Аудиофайлы внутри папки книги, отсортированные по имени."""
    prefix = book_prefix(book_id)

    def producer() -> list[dict]:
        data = _list_objects(prefix, delimiter="/")
        files = [
            {
                "id": obj["Key"],                 # полный ключ — уникален в бакете
                "name": filename_of(obj["Key"]),
                "size": obj.get("Size", 0),
                "mimeType": guess_audio_mime(obj["Key"]),
            }
            for obj in data["contents"]
            if is_audio_key(obj["Key"])
        ]
        files.sort(key=lambda f: f["name"].lower())
        return files

    return _cached(f"audio:{prefix}", producer, bypass=bypass_cache)


def find_cover_image(book_id: str) -> dict | None:
    """
    Обложка книги.

    Сначала ищем файл, чьё имя начинается на 'cover' — это явный признак.
    Если такого нет, берём первое изображение по алфавиту — на случай, когда
    обложку назвали как угодно («Обложка.jpg», «1.png» и т.п.).
    """
    prefix = book_prefix(book_id)

    def producer() -> dict | None:
        data = _list_objects(prefix, delimiter="/")
        images = [obj for obj in data["contents"] if is_cover_key(obj["Key"])]
        if not images:
            return None

        for obj in images:
            name = filename_of(obj["Key"]).lower()
            if name.startswith("cover"):
                return {"id": obj["Key"], "name": filename_of(obj["Key"])}

        first = min(images, key=lambda o: filename_of(o["Key"]).lower())
        return {"id": first["Key"], "name": filename_of(first["Key"])}

    return _cached(f"cover:{prefix}", producer)


def find_annotation_file(book_id: str) -> dict | None:
    """Ищет text.txt в папке книги (без учёта регистра)."""
    prefix = book_prefix(book_id)

    def producer() -> dict | None:
        data = _list_objects(prefix, delimiter="/")
        for obj in data["contents"]:
            name = filename_of(obj["Key"])
            if name.strip().lower() == ANNOTATION_FILENAME:
                return {"id": obj["Key"], "name": name}
        return None

    return _cached(f"annotation:{prefix}", producer)


def read_annotation_file(key: str) -> str:
    """Скачивает text.txt из бакета и декодирует в UTF-8."""
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=get_bucket(), Key=key)
        raw = response["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        raise StorageClientError(f"Не удалось прочитать {key}: {exc}") from exc

    for encoding in ("utf-8-sig", "utf-8", "cp1251", "utf-16"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


def object_exists(key: str) -> bool:
    client = get_s3_client()
    try:
        client.head_object(Bucket=get_bucket(), Key=key)
        return True
    except ClientError:
        return False
    except BotoCoreError as exc:
        raise StorageClientError(f"Не удалось проверить {key}: {exc}") from exc


# ---------- Подписанные ссылки ----------

# Максимум для Yandex Object Storage — 7 суток.
DEFAULT_AUDIO_URL_TTL = int(os.getenv("S3_AUDIO_URL_TTL", "86400"))   # 24 часа
DEFAULT_COVER_URL_TTL = int(os.getenv("S3_COVER_URL_TTL", "86400"))   # 24 часа


def get_presigned_url(
    key: str,
    expires_in: int,
    content_type: str | None = None,
    download_name: str | None = None,
) -> str:
    """
    Подписывает ссылку на объект.

    Важно: подпись считается локально (HMAC), без обращения к сети. Поэтому
    можно подписать хоть сотню ссылок на одну выдачу списка глав — это дёшево
    и не создаёт нагрузки при тысяче одновременных слушателей.

    content_type и download_name уезжают в query-параметры response-content-type
    и response-content-disposition. Так мы отдаём браузеру правильный MIME-тип
    даже если объект залит как application/octet-stream.
    """
    params: dict[str, Any] = {"Bucket": get_bucket(), "Key": key}
    if content_type:
        params["ResponseContentType"] = content_type
    if download_name:
        params["ResponseContentDisposition"] = f'inline; filename="{download_name}"'

    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageClientError(f"Не удалось подписать ссылку на {key}: {exc}") from exc


def audio_url(key: str, expires_in: int | None = None) -> str:
    return get_presigned_url(
        key,
        expires_in or DEFAULT_AUDIO_URL_TTL,
        content_type=guess_audio_mime(key),
    )


def cover_url(key: str, expires_in: int | None = None) -> str:
    return get_presigned_url(
        key,
        expires_in or DEFAULT_COVER_URL_TTL,
        content_type=guess_cover_mime(key),
    )


# ---------- Парсер аннотации ----------
# Логика не менялась при переезде — формат text.txt остался прежним.


def parse_annotation(raw: str) -> dict:
    """
    Разбирает text.txt и вытаскивает теги, чтеца и текст аннотации.

    Любая строка, начинающаяся с распознанной директивы, считается метаданными
    и убирается из тела аннотации. Порядок строк значения не имеет:

        #теги: Тег1, Тег2, Тег3
        #чтец: Имя Чтеца

        Текст аннотации — всё остальное.

    Чтец дополнительно попадает в список тегов, чтобы по нему можно было фильтровать.
    """
    tags: list[str] = []
    narrator: str = ""
    body_lines: list[str] = []

    for line in raw.splitlines():
        low = line.strip().lower()
        if low.startswith("#теги:"):
            raw_tags = line.strip()[len("#теги:"):].strip()
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif low.startswith("#чтец:"):
            narrator = line.strip()[len("#чтец:"):].strip()
        else:
            body_lines.append(line)

    annotation = "\n".join(body_lines).strip()

    if narrator and narrator not in tags:
        tags.append(narrator)

    return {
        "tags": tags,
        "narrator": narrator,
        "annotation": annotation,
    }


EMPTY_ANNOTATION = {"tags": [], "narrator": "", "annotation": ""}
