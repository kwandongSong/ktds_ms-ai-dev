# storage_logs.py
from datetime import datetime
import uuid
from typing import Optional

from azure.data.tables import TableServiceClient, UpdateMode
from azure.core.credentials import AzureNamedKeyCredential
from config import CONFIG

_TABLE_NAME = CONFIG.get("ACTIVITY_TABLE_NAME", "DocspaceActivity")

def _get_table_service_client() -> TableServiceClient:
    """
    1) AZURE_STORAGE_CONNECTION_STRING 있으면 우선 사용
    2) 없으면 endpoint + AzureNamedKeyCredential(account, key) 사용
    """
    conn_str: Optional[str] = CONFIG.get("AZURE_STORAGE_CONNECTION_STRING")
    account = CONFIG["AZURE_STORAGE_ACCOUNT"]
    key = CONFIG["AZURE_STORAGE_KEY"]

    if conn_str:
        # 연결 문자열 방식
        return TableServiceClient.from_connection_string(conn_str)

    # 엔드포인트 + 명명 키 자격증명
    endpoint = f"https://{account}.table.core.windows.net"
    credential = AzureNamedKeyCredential(account, key)
    return TableServiceClient(endpoint=endpoint, credential=credential)

def _get_table_client():
    svc = _get_table_service_client()
    try:
        svc.create_table_if_not_exists(_TABLE_NAME)
    except Exception:
        # 이미 존재/경합 등은 무시
        pass
    return svc.get_table_client(_TABLE_NAME)

def ensure_table():
    """
    테이블 존재 보장 (없으면 생성)
    """
    _get_table_client()
    return _TABLE_NAME

def log_activity(user_id: str, source: str, level: str, message: str):
    """
    활동 로그 기록
    PartitionKey: user_id (미지정 시 'default' 권장)
    RowKey: uuid4
    """
    table = _get_table_client()
    entity = {
        "PartitionKey": user_id or "default",
        "RowKey": str(uuid.uuid4()),
        "CreatedAt": datetime.utcnow().isoformat(),
        "Source": source,
        "Level": level,
        "Message": message[:32000],  # 과도한 길이 방지
    }
    table.upsert_entity(entity, mode=UpdateMode.MERGE)

def query_recent(top: int = 50, user_id: str = "default"):
    """
    최근 로그 상위 N건 (PartitionKey 기준)
    """
    table = _get_table_client()
    results = table.query_entities(f"PartitionKey eq '{user_id}'")
    out = []
    for ent in results:
        out.append(ent)
        if len(out) >= top:
            break
    out.sort(key=lambda x: x.get("CreatedAt", ""), reverse=True)
    return out
