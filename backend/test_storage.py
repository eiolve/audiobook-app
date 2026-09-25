"""
Проверка storage_client на локальном моке S3 (moto).

Запуск из корня репозитория:
    python3 backend/test_storage.py

Скрипт заливает в фейковый бакет «книгу» с обложкой, text.txt и двумя
аудиофайлами, после чего проверяет, что клиент видит ровно то, что должен:
список книг, список глав, обложку, разобранные теги и подписанные ссылки.
"""

import os
import sys

# Переменные окружения должны быть выставлены ДО импорта storage_client,
# потому что клиент S3 создаётся лениво, но читает настройки при первом вызове.
os.environ.update(
    {
        "S3_BUCKET": "test-bucket",
        "S3_ENDPOINT": "https://s3.amazonaws.com",
        "S3_REGION": "ru-central1",
        "S3_ACCESS_KEY": "test-key",
        "S3_SECRET_KEY": "test-secret",
        "S3_BOOKS_PREFIX": "books/",
        "S3_CACHE_TTL": "0",  # отключаем кэш, чтобы тесты видели свежие данные
    }
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

import storage_client as sc  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


ANNOTATION = """#теги: Фэнтези, Эпик, Тёмное
#чтец: Иван Петров

Первая книга цикла. Мир на грани войны, древние силы пробуждаются.
Вторая строка аннотации."""


@mock_aws
def run() -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    # --- заливаем структуру, как её положит rclone ---
    s3.put_object(Bucket="test-bucket", Key="books/Ересь Хоруса/cover.jpg", Body=b"fake-jpeg")
    s3.put_object(
        Bucket="test-bucket",
        Key="books/Ересь Хоруса/text.txt",
        Body=ANNOTATION.encode("utf-8"),
    )
    s3.put_object(
        Bucket="test-bucket",
        Key="books/Ересь Хоруса/01 - Пролог.mp3",
        Body=b"a" * 1024,
    )
    s3.put_object(
        Bucket="test-bucket",
        Key="books/Ересь Хоруса/02 - Глава первая.mp3",
        Body=b"b" * 2048,
    )
    # файл, который не должен попасть в список глав
    s3.put_object(Bucket="test-bucket", Key="books/Ересь Хоруса/readme.pdf", Body=b"pdf")

    # вторая книга — без обложки и без аннотации
    s3.put_object(Bucket="test-bucket", Key="books/Пустая книга/01.mp3", Body=b"c" * 512)

    print("\n=== Список книг ===")
    books = sc.list_book_folders()
    for b in books:
        print("   ", b)
    check("найдены ровно 2 книги", len(books) == 2, f"получено {len(books)}")
    check(
        "книги отсортированы по имени",
        [b["id"] for b in books] == ["Ересь Хоруса", "Пустая книга"],
        str([b["id"] for b in books]),
    )
    check("кириллица в id не потерялась", books[0]["id"] == "Ересь Хоруса", books[0]["id"])

    print("\n=== Главы ===")
    chapters = sc.list_audio_files("Ересь Хоруса")
    for c in chapters:
        print("   ", c)
    check("найдены 2 главы (pdf отфильтрован)", len(chapters) == 2, f"получено {len(chapters)}")
    check(
        "главы отсортированы по имени",
        [c["name"] for c in chapters] == ["01 - Пролог.mp3", "02 - Глава первая.mp3"],
        str([c["name"] for c in chapters]),
    )
    check(
        "id главы — полный ключ",
        chapters[0]["id"] == "books/Ересь Хоруса/01 - Пролог.mp3",
        chapters[0]["id"],
    )
    check("размер главы прочитан", chapters[0]["size"] == 1024, str(chapters[0]["size"]))
    check("MIME для mp3 верный", chapters[0]["mimeType"] == "audio/mpeg", chapters[0]["mimeType"])

    print("\n=== Обложка ===")
    cover = sc.find_cover_image("Ересь Хоруса")
    print("   ", cover)
    check("обложка найдена", cover is not None)
    check("это именно cover.jpg", cover and cover["id"].endswith("cover.jpg"), str(cover))
    check("у книги без обложки — None", sc.find_cover_image("Пустая книга") is None)

    print("\n=== Аннотация ===")
    ann_file = sc.find_annotation_file("Ересь Хоруса")
    check("text.txt найден", ann_file is not None, str(ann_file))
    check("text.txt не найден там, где его нет", sc.find_annotation_file("Пустая книга") is None)

    raw = sc.read_annotation_file(ann_file["id"])
    parsed = sc.parse_annotation(raw)
    print("    теги:    ", parsed["tags"])
    print("    чтец:    ", parsed["narrator"])
    print("    аннот.:  ", parsed["annotation"])
    check("теги разобраны", parsed["tags"][:3] == ["Фэнтези", "Эпик", "Тёмное"], str(parsed["tags"]))
    check("чтец разобран", parsed["narrator"] == "Иван Петров", parsed["narrator"])
    check("чтец добавлен в теги", "Иван Петров" in parsed["tags"])
    check(
        "директивы убраны из тела аннотации",
        "#теги" not in parsed["annotation"] and "#чтец" not in parsed["annotation"],
        parsed["annotation"][:80],
    )
    check(
        "текст аннотации сохранён",
        parsed["annotation"].startswith("Первая книга цикла"),
        parsed["annotation"][:60],
    )

    print("\n=== Подписанные ссылки ===")
    url = sc.audio_url(chapters[0]["id"])
    print("    ", url[:130], "...")
    check("ссылка непустая", bool(url))
    check("это подпись v4", "X-Amz-Signature" in url, url[:100])
    check("Content-Type подставлен", "audio%2Fmpeg" in url or "audio/mpeg" in url, url[:160])
    check("срок жизни задан", "X-Amz-Expires=86400" in url, url[:200])

    cover_url = sc.cover_url(cover["id"])
    print("    ", cover_url[:130], "...")
    check("обложка подписана как image/jpeg", "image%2Fjpeg" in cover_url or "image/jpeg" in cover_url)

    print("\n=== Утилиты путей ===")
    check("префикс книги", sc.book_prefix("Ересь Хоруса") == "books/Ересь Хоруса/", sc.book_prefix("Ересь Хоруса"))
    check("определение аудио", sc.is_audio_key("books/a/01.MP3") is True)
    check("pdf не аудио", sc.is_audio_key("books/a/readme.pdf") is False)
    check("m4b — аудио", sc.guess_audio_mime("x.m4b") == "audio/mp4")
    check("wav — аудио", sc.guess_audio_mime("x.wav") == "audio/wav")

    print("\n=== Кэш ===")
    sc.invalidate_cache()
    check("кэш очищается", sc._CACHE == {}, str(sc._CACHE))


if __name__ == "__main__":
    run()
    print("\n" + "=" * 50)
    if FAILURES:
        print(f"ПРОВАЛЕНО: {len(FAILURES)}")
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
