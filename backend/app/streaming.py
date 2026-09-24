"""
Стриминг аудиофайла с Google Drive на клиент с поддержкой Range-запросов.

Почему это отдельный модуль и зачем так сложно:
Google Drive REST API (`files.get?alt=media`) поддерживает заголовок Range,
но браузерный <audio> плеер шлёт Range-запросы постоянно (перемотка, докачка
буфера). Мы проксируем эти запросы 1:1 на Google, передавая тот же Range,
и отдаём клиенту тот же статус (206 Partial Content) и заголовки.
Это даёт нормальную перемотку без скачивания всего файла целиком.
"""
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from .drive_client import get_credentials_token, get_file_metadata

DRIVE_DOWNLOAD_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"


async def stream_drive_file(
    file_id: str, request: Request, default_mime: str = "audio/mpeg"
) -> StreamingResponse:
    """
    Проксирует файл с Google Drive клиенту.

    Используется и для аудио (с Range-запросами для перемотки), и для
    изображений обложек (без Range — картинки маленькие, отдаются целиком).
    """
    try:
        metadata = get_file_metadata(file_id)
    except Exception as exc:  # noqa: BLE001 — отдаём понятную ошибку клиенту
        raise HTTPException(status_code=404, detail=f"Файл не найден на Drive: {exc}") from exc

    token = get_credentials_token()
    headers = {"Authorization": f"Bearer {token}"}

    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    url = DRIVE_DOWNLOAD_URL.format(file_id=file_id)

    client = httpx.AsyncClient(timeout=None)
    upstream_request = client.build_request("GET", url, headers=headers)
    upstream_response = await client.send(upstream_request, stream=True)

    if upstream_response.status_code not in (200, 206):
        body = await upstream_response.aread()
        await upstream_response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=upstream_response.status_code,
            detail=f"Google Drive вернул ошибку: {body[:200]!r}",
        )

    response_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": metadata.get("mimeType", default_mime),
        "Cache-Control": "public, max-age=86400",
    }
    for key in ("content-range", "content-length"):
        if key in upstream_response.headers:
            response_headers[key.title()] = upstream_response.headers[key]

    async def body_iterator():
        try:
            async for chunk in upstream_response.aiter_bytes(chunk_size=64 * 1024):
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()

    return StreamingResponse(
        body_iterator(),
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
