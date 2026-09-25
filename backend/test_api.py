"""
Проверка API-эндпоинтов на моке S3.

Запуск из корня репозитория:
    python3 backend/test_api.py

Поднимает FastAPI-приложение поверх фейкового бакета и проверяет,
что фронтенд получит именно те поля, которые ожидает.
"""

import os
import sys

os.environ.update(
    {
        "S3_BUCKET": "test-bucket",
        "S3_ENDPOINT": "https://s3.amazonaws.com",
        "S3_REGION": "ru-central1",
        "S3_ACCESS_KEY": "test-key",
        "S3_SECRET_KEY": "test-secret",
        "S3_BOOKS_PREFIX": "books/",
        "S3_CACHE_TTL": "0",
        "DATABASE_PATH": "/tmp/test_audiobook.db",
        "DISABLE_TELEGRAM_AUTH": "true",
    }
)

sys.path.insert(0, os.path.dirname(__file__))

import boto3  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402

from app import main  # noqa: E402

ANNOTATION = "#теги: Фэнтези, Эпик\n#чтец: Иван Петров\n\nАннотация первой книги."

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


@mock_aws
def run() -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    s3.put_object(Bucket="test-bucket", Key="books/Ересь Хоруса/cover.jpg", Body=b"jpeg")
    s3.put_object(Bucket="test-bucket", Key="books/Ересь Хоруса/text.txt", Body=ANNOTATION.encode())
    s3.put_object(Bucket="test-bucket", Key="books/Ересь Хоруса/01 - Пролог.mp3", Body=b"a" * 4096)
    s3.put_object(Bucket="test-bucket", Key="books/Ересь Хоруса/02 - Глава.mp3", Body=b"b" * 8192)

    client = TestClient(main.app)
    # Таблицу создаём явно: при использовании TestClient как контекстного
    # менеджера startup отработал бы сам, но нам нужен обычный клиент.
    main.init_db()

    print("\n=== GET /api/health ===")
    r = client.get("/api/health")
    print("   ", r.status_code, r.json())
    check("health отвечает 200", r.status_code == 200, str(r.status_code))
    check("health показывает бакет", r.json().get("storage") == "test-bucket", str(r.json()))

    print("\n=== GET /api/books ===")
    r = client.get("/api/books")
    books = r.json()
    print("   ", r.status_code)
    for b in books:
        print("    -", b["title"], "| теги:", b["tags"], "| обложка:", bool(b["coverUrl"]))
    check("статус 200", r.status_code == 200, str(r.status_code))
    check("одна книга", len(books) == 1, str(len(books)))
    check("title = имя папки", books[0]["title"] == "Ересь Хоруса", books[0]["title"])
    check("id = имя папки", books[0]["id"] == "Ересь Хоруса", books[0]["id"])
    check("теги на месте", books[0]["tags"] == ["Фэнтези", "Эпик", "Иван Петров"], str(books[0]["tags"]))
    check("narrator на месте", books[0]["narrator"] == "Иван Петров", books[0]["narrator"])
    check("coverUrl — подписанная ссылка", "X-Amz-Signature" in (books[0]["coverUrl"] or ""), str(books[0]["coverUrl"])[:80])
    check("старое поле coverFileId убрано", "coverFileId" not in books[0])

    print("\n=== GET /api/books/{id}/chapters ===")
    r = client.get("/api/books/Ересь Хоруса/chapters")
    payload = r.json()
    print("   ", r.status_code, "| глав:", len(payload.get("chapters", [])))
    for ch in payload.get("chapters", []):
        print("    -", ch["title"], "|", ch["sizeBytes"], "байт | streamUrl:", bool(ch.get("streamUrl")))
    check("статус 200", r.status_code == 200, str(r.status_code))
    check("две главы", len(payload["chapters"]) == 2, str(len(payload.get("chapters", []))))
    check("аннотация отдана", payload["annotation"].startswith("Аннотация первой книги"), payload["annotation"][:40])
    check("теги отданы", payload["tags"] == ["Фэнтези", "Эпик", "Иван Петров"], str(payload["tags"]))
    check("coverUrl отдан", "X-Amz-Signature" in (payload["coverUrl"] or ""))
    check("streamUrl у каждой главы", all("X-Amz-Signature" in ch["streamUrl"] for ch in payload["chapters"]))
    check("sizeBytes проставлен", payload["chapters"][0]["sizeBytes"] == 4096, str(payload["chapters"][0]["sizeBytes"]))
    check("mimeType проставлен", payload["chapters"][0]["mimeType"] == "audio/mpeg")

    print("\n=== GET /api/stream-url/{key} — ключ с кириллицей и слэшами ===")
    key = payload["chapters"][0]["id"]
    from urllib.parse import quote
    r = client.get(f"/api/stream-url/{quote(key, safe='')}")
    print("   ", r.status_code, str(r.json())[:100])
    check("статус 200", r.status_code == 200, str(r.status_code))
    check("свежая ссылка выдана", "X-Amz-Signature" in r.json().get("streamUrl", ""))

    print("\n=== GET /api/stream/{key} — редирект для совместимости ===")
    r = client.get(f"/api/stream/{quote(key, safe='')}", follow_redirects=False)
    print("   ", r.status_code, r.headers.get("location", "")[:90])
    check("отдаёт 302", r.status_code == 302, str(r.status_code))
    check("ведёт на подписанную ссылку", "X-Amz-Signature" in r.headers.get("location", ""))
    check("это НЕ адрес backend (раздача мимо сервера)", "storage" in r.headers.get("location", "") or "s3" in r.headers.get("location", ""))

    print("\n=== GET /api/cover/{key} ===")
    cover_key = "books/Ересь Хоруса/cover.jpg"
    r = client.get(f"/api/cover/{quote(cover_key, safe='')}", follow_redirects=False)
    check("обложка: 302", r.status_code == 302, str(r.status_code))
    check("обложка: image/jpeg в ссылке", "image" in r.headers.get("location", ""))

    print("\n=== Прогресс ===")
    r = client.post("/api/progress", json={"user_id": "u1", "file_id": key, "position_seconds": 42.5})
    check("сохранение прогресса", r.status_code == 200 and r.json() == {"ok": True}, str(r.json()))
    r = client.get("/api/progress/u1")
    check("чтение прогресса", r.json().get(key) == 42.5, str(r.json()))

    print("\n=== Ошибки ===")
    r = client.get("/api/books/Несуществующая/chapters")
    check("несуществующая книга -> 404", r.status_code == 404, str(r.status_code))

    print("\n=== GET /api/debug/books ===")
    r = client.get("/api/debug/books")
    dbg = r.json()
    print("   ", r.status_code, "| аудио:", dbg[0]["audio_count"], "| обложка:", dbg[0]["cover"])
    check("диагностика работает", r.status_code == 200, str(r.status_code))
    check("диагностика считает аудио", dbg[0]["audio_count"] == 2, str(dbg[0]["audio_count"]))
    check("диагностика видит text.txt", dbg[0]["annotation_file"] == "text.txt", str(dbg[0]["annotation_file"]))


if __name__ == "__main__":
    run()
    print("\n" + "=" * 50)
    if FAILURES:
        print(f"ПРОВАЛЕНО: {len(FAILURES)}")
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ API ПРОЙДЕНЫ")
