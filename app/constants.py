from __future__ import annotations

from typing import Final


NAPCAT_ONEBOT11_JSON_CANDIDATES: Final[tuple[str, ...]] = (
    '/opt/napcat-home/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/onebot11.json',
    '/opt/QQ/resources/app/app_launcher/napcat/config/onebot11.json',
)

MAX_INGEST_IMAGE_BYTES: Final[int] = 15 * 1024 * 1024

ALLOWED_IMAGE_EXTS: Final[set[str]] = {
    '.png',
    '.jpg',
    '.jpeg',
    '.webp',
    '.gif',
    '.bmp',
    '.tif',
    '.tiff',
    '.ico',
}

