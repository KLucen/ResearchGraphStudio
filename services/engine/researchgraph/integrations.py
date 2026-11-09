"""Read-only Zotero Local API adapter for the Lite importer."""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from researchgraph.core import KnowledgeError


class LocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class ZoteroAdapter:
    base = "http://127.0.0.1:23119/api"

    @staticmethod
    def library(value: str) -> str:
        if not re.fullmatch(r"(?:users|groups)/[0-9]{1,16}", value):
            raise KnowledgeError("INVALID_LIBRARY", "Zotero library 必须为 users/0 或 groups/数字")
        return value

    @staticmethod
    def key(value: str) -> str:
        if not re.fullmatch(r"[A-Z0-9]{8}", value):
            raise KnowledgeError("INVALID_ZOTERO_KEY", "Zotero Key 必须为 8 位大写字母/数字")
        return value

    def get(self, route: str) -> Any:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirect())
            with opener.open(self.base + route, timeout=5) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise KnowledgeError("ZOTERO_RESPONSE_TOO_LARGE", "Zotero 响应超过限制")
            return json.loads(raw)
        except KnowledgeError:
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise KnowledgeError(
                "ZOTERO_UNAVAILABLE", "Zotero Local API 未启动、未授权或响应无效"
            ) from error

    def browse(self, library: str, kind: str, start: int = 0) -> list[dict[str, Any]]:
        value = self.get(f"/{self.library(library)}/{kind}?limit=50&start={start}")
        if not isinstance(value, list):
            raise KnowledgeError("ZOTERO_INVALID_RESPONSE", "Zotero 列表响应无效")
        return value

    def attachment_path(self, library: str, key: str) -> Path:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirect())
            with opener.open(
                self.base + f"/{self.library(library)}/items/{self.key(key)}/file/view", timeout=5
            ):
                raise KnowledgeError("ZOTERO_FILE_UNAVAILABLE", "Zotero 未返回本地附件位置")
        except urllib.error.HTTPError as error:
            location = error.headers.get("Location", "")
            parsed = urllib.parse.urlsplit(location)
            if (
                error.code not in {301, 302, 303, 307, 308}
                or parsed.scheme != "file"
                or parsed.netloc not in {"", "localhost"}
            ):
                raise KnowledgeError(
                    "ZOTERO_FILE_UNAVAILABLE", "Zotero 附件未同步或无法定位"
                ) from None
            return Path(urllib.request.url2pathname(parsed.path))
        except KnowledgeError:
            raise
        except (urllib.error.URLError, TimeoutError) as error:
            raise KnowledgeError("ZOTERO_UNAVAILABLE", "无法定位 Zotero 本地附件") from error
