from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}


@dataclass
class GentleClient:
    cache_dir: Path
    min_delay: float = 1.0
    max_delay: float = 2.2
    timeout: float = 25.0
    verify_ssl: bool = True
    use_cache: bool = True

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _sleep(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        host = urlparse(url).netloc.replace(":", "_")
        return self.cache_dir / f"{host}_{digest}.json"

    def fetch_text(self, url: str, force: bool = False) -> str:
        cache_path = self._cache_path(url)
        if self.use_cache and cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return payload["text"]

        self._sleep()
        response = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
        response.raise_for_status()

        text = response.text
        if self.use_cache:
            cache_path.write_text(
                json.dumps(
                    {
                        "url": url,
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "text": text,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return text

    def fetch_json(self, url: str, force: bool = False) -> Any:
        text = self.fetch_text(url, force=force)
        return json.loads(text)
