"""Windows Credential Manager. Never falls back to plaintext files or SQLite."""

import ctypes
import hashlib
import os
from ctypes import wintypes
from pathlib import Path


class CredentialError(ValueError):
    pass


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class SecretStore:
    def __init__(self, data_dir: Path):
        self.namespace = hashlib.sha256(str(data_dir.resolve()).encode()).hexdigest()[:24]

    def _api(self) -> ctypes.WinDLL:
        if os.name != "nt":
            raise CredentialError("此平台尚未配置安全凭据后端，不能保存 API Key")
        return ctypes.WinDLL("Advapi32.dll", use_last_error=True)

    def target(self, reference: str) -> str:
        from uuid import UUID

        UUID(reference)
        return f"ResearchGraphStudio/{self.namespace}/{reference}"

    def put(self, reference: str, secret: str) -> None:
        raw = secret.encode("utf-8")
        if not raw or len(raw) > 2400:
            raise CredentialError("API Key 必须为 1–2400 字节")
        api = self._api()
        api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        entry = Credential()
        entry.Type, entry.Persist = 1, 2
        entry.TargetName, entry.UserName = self.target(reference), "ResearchGraphStudio"
        entry.CredentialBlob, entry.CredentialBlobSize = blob, len(raw)
        if not api.CredWriteW(ctypes.byref(entry), 0):
            raise CredentialError("Windows 凭据管理器保存失败；未使用明文降级存储")

    def get(self, reference: str) -> str:
        api = self._api()
        pointer = ctypes.POINTER(Credential)()
        api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(Credential)),
        ]
        api.CredReadW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        if not api.CredReadW(self.target(reference), 1, 0, ctypes.byref(pointer)):
            raise CredentialError("API Key 不可读取，请在全局设置与诊断中重新保存")
        try:
            entry = pointer.contents
            return ctypes.string_at(entry.CredentialBlob, entry.CredentialBlobSize).decode("utf-8")
        finally:
            api.CredFree(pointer)

    def delete(self, reference: str) -> None:
        api = self._api()
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        if not api.CredDeleteW(self.target(reference), 1, 0) and ctypes.get_last_error() != 1168:
            raise CredentialError("Windows 凭据删除失败，可稍后重试")
