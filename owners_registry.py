# owners_registry.py
from typing import Optional, Dict
import os, base64
from azure.data.tables import TableServiceClient, TableClient, UpdateMode
from azure.core.exceptions import (
    ResourceExistsError, ResourceNotFoundError, ClientAuthenticationError, HttpResponseError
)
from config import CONFIG
from azure.core.credentials import AzureNamedKeyCredential

_TABLE = "DocspaceOwners"
_FALLBACK: Dict[str, Dict[str, str]] = {}  # originalId -> {"email":..., "phone":...}

# ─────────────────────────────────────────────────────────
# RowKey 안전 변환: URL-safe Base64 (padding 제거)
# ─────────────────────────────────────────────────────────
def _safe_rowkey(raw: str) -> str:
    if not raw:
        raise ValueError("originalId is empty")
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")

def _get_table_service_client() -> TableServiceClient:
    conn = CONFIG.get("AZURE_STORAGE_CONNECTION_STRING") or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if conn:
        return TableServiceClient.from_connection_string(conn)

    account = CONFIG.get("AZURE_STORAGE_ACCOUNT") or os.getenv("AZURE_STORAGE_ACCOUNT")
    key = CONFIG.get("AZURE_STORAGE_KEY") or os.getenv("AZURE_STORAGE_KEY")
    if not (account and key):
        raise RuntimeError("Storage 자격증명이 없습니다. AZURE_STORAGE_CONNECTION_STRING 또는 (AZURE_STORAGE_ACCOUNT + AZURE_STORAGE_KEY) 설정 필요")

    endpoint = CONFIG.get("AZURE_TABLE_ENDPOINT") or f"https://{account}.table.core.windows.net"
    
    credential = AzureNamedKeyCredential(account, key)
    return TableServiceClient(endpoint=endpoint, credential=credential)

def ensure_owners_table() -> TableClient:
    svc = _get_table_service_client()
    svc.create_table_if_not_exists(_TABLE)
    try:
        svc = svc.get_table_client(_TABLE)
    except ResourceExistsError:
        pass
    return svc

# ─────────────────────────────────────────────────────────
# Public APIs
# ─────────────────────────────────────────────────────────
def set_owner(original_id: str, email: Optional[str], phone: Optional[str]) -> Dict[str, str]:
    tc = ensure_owners_table()
    row = _safe_rowkey(original_id)

    entity = {
        "PartitionKey": "Owner",
        "RowKey": row,
        "OriginalId": original_id,
        "Email": (email or "").strip(),
        "Phone": (phone or "").strip(),
    }

    # ✅ 가장 호환 잘 되는 MERGE 사용 (없으면 insert, 있으면 부분 갱신)
    tc.upsert_entity(entity=entity, mode=UpdateMode.MERGE)
    # 만약 구버전 SDK라 Enum을 못 받으면:
    # tc.upsert_entity(entity=entity, mode="merge")  # ← 소문자

    # 저장 검증(강제 read-back)
    saved = tc.get_entity(partition_key="Owner", row_key=row)
    return {
        "OriginalId": saved.get("OriginalId"),
        "Email": saved.get("Email"),
        "Phone": saved.get("Phone"),
        "_RowKey": row,
        "_Table": _TABLE,
    }

def get_owner(original_id: str) -> Dict[str, str]:
    email_fallback = CONFIG.get("DEFAULT_OWNER_EMAIL", "")
    phone_fallback = CONFIG.get("DEFAULT_OWNER_PHONE", "")
    if not original_id:
        return {"email": email_fallback, "phone": phone_fallback}

    try:
        tc = ensure_owners_table()
        ent = tc.get_entity(partition_key="Owner", row_key=_safe_rowkey(original_id))
        return {
            "email": ent.get("Email") or email_fallback,
            "phone": ent.get("Phone") or phone_fallback
        }
    except Exception:
        info = _FALLBACK.get(original_id) or {}
        return {"email": info.get("email") or email_fallback, "phone": info.get("phone") or phone_fallback}

def diag_tables() -> Dict[str, str]:
    out = {}
    try:
        svc = _get_table_service_client()
        out["endpoint"] = getattr(svc, "url", "unknown")
        names = [t.name for i, t in enumerate(svc.list_tables()) if i < 10]
        out["tables_sample"] = ", ".join(names) if names else "(none)"
        out["ok"] = "true"
    except Exception as e:
        out["ok"] = "false"
        out["error"] = repr(e)
    return out
