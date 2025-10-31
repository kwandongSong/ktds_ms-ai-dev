import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

import azure.functions as func
import requests
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableServiceClient

# ─────────────────────────────────────────
# 환경 변수 헬퍼
# ─────────────────────────────────────────
def _cfg(k: str, default: str = "") -> str:
    return os.environ.get(k, default)

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ─────────────────────────────────────────
# Azure Cognitive Search: 오래된 문서 샘플 조회
# ─────────────────────────────────────────
def search_docs_top_oldest(endpoint: str, index: str, api_key: str, top: int) -> List[Dict]:
    if not (endpoint and index and api_key):
        return []
    url = f"{endpoint.rstrip('/')}/indexes('{index}')/docs/search?api-version=2023-11-01"
    # lastModified 오름차순 → 오래된 것부터
    body = {
        "search": "*",
        "select": "id,originalId,name,lastModified,source,path",
        "top": top,
        "queryType": "simple",
        "orderby": "lastModified asc"
    }
    r = requests.post(url, headers={"Content-Type": "application/json", "api-key": api_key}, json=body, timeout=30)
    r.raise_for_status()
    return r.json().get("value", [])

# ─────────────────────────────────────────
# 활동 로그(Table): 별도 계정/키 사용 (없으면 생략)
# ─────────────────────────────────────────
def fetch_recent_activity(limit: int = 50) -> List[Dict]:
    table_acct = _cfg("TABLE_ACCOUNT")
    table_key  = _cfg("TABLE_KEY")
    table_ep   = _cfg("TABLE_ENDPOINT")  # 예: https://pressmstore22165.table.core.windows.net
    table_name = _cfg("TABLE_NAME", "DocspaceActivity")
    if not (table_acct and table_key and table_ep):
        return []
    svc = TableServiceClient(endpoint=table_ep, credential=table_key)
    tc  = svc.get_table_client(table_name)
    # 테이블이 없다면 읽기 스킵(필요 시 생성 로직 추가 가능)
    try:
        rows = []
        # 테이블 쿼리는 정렬이 없어 상위 N 개만 슬라이싱
        for page in tc.list_entities(results_per_page=limit).by_page():
            for ent in page:
                rows.append(ent)
                if len(rows) >= limit:
                    return rows
        return rows
    except Exception:
        return []

# ─────────────────────────────────────────
# 결과 Markdown 빌더
# ─────────────────────────────────────────
def build_markdown(docs: List[Dict], days_threshold: int, activities: List[Dict], title: str) -> str:
    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc - timedelta(days=days_threshold)

    stale = []
    for d in docs:
        lm = d.get("lastModified")
        try:
            lm_dt = datetime.fromisoformat(str(lm).replace("Z", "+00:00"))
        except Exception:
            lm_dt = None
        if lm_dt and lm_dt < cutoff:
            stale.append(d)

    lines = []
    lines.append(f"# {title or 'DocSpace AI – Consolidated Report'}")
    lines.append("")
    lines.append(f"_Generated at (UTC) {_utc_now_iso()}_")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Total Indexed (sampled): **{len(docs)}**")
    lines.append(f"- Stale Threshold: **{days_threshold} days**")
    lines.append(f"- Stale Found (within sample): **{len(stale)}**")
    lines.append("")

    if stale:
        lines.append("## Stale Documents")
        for s in stale[:100]:
            nm   = s.get("name", "-")
            oid  = s.get("originalId", s.get("id"))
            lm   = s.get("lastModified", "-")
            src  = s.get("source", "-")
            path = s.get("path", "")
            suffix = f" · {path}" if path else ""
            lines.append(f"- **{nm}** _(src: {src}, lastModified: {lm})_  \n  id: `{oid}`{suffix}")
        lines.append("")

    if activities:
        lines.append("## Recent Activities")
        for a in activities[:50]:
            t   = a.get("CreatedAt") or a.get("Timestamp") or "-"
            lvl = a.get("Level") or "-"
            src = a.get("Source") or "-"
            msg = a.get("Message") or ""
            msg = (msg[:140] + "…") if len(msg) > 140 else msg
            lines.append(f"- `{t}` [{lvl}] ({src}) {msg}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"

# ─────────────────────────────────────────
# Blob 저장 (DATA_STORAGE_ACCOUNT / DATA_STORAGE_KEY 사용)
# ─────────────────────────────────────────
def save_blob_markdown(markdown_text: str, file_name: str, container: str) -> str:
    account = _cfg("DATA_STORAGE_ACCOUNT")
    key     = _cfg("DATA_STORAGE_KEY")
    if not (account and key):
        raise RuntimeError("DATA_STORAGE_ACCOUNT/DATA_STORAGE_KEY is required")

    # Blob은 blob.core.windows.net 사용 (table endpoint는 별개입니다)
    bsc = BlobServiceClient(account_url=f"https://{account}.blob.core.windows.net", credential=key)
    try:
        bsc.create_container(container)
    except Exception:
        pass
    blob = bsc.get_blob_client(container, file_name)
    blob.upload_blob(markdown_text.encode("utf-8"), overwrite=True, content_type="text/markdown")
    return f"{container}/{file_name}"

# (선택) Teams Webhook 알림
def send_teams(webhook_url: str, title: str, text: str):
    if not webhook_url:
        return
    card = {"title": title, "text": text}
    try:
        requests.post(webhook_url, headers={"Content-Type": "application/json"}, data=json.dumps(card), timeout=15)
    except Exception:
        pass

# ─────────────────────────────────────────
# 타이머 엔트리
# ─────────────────────────────────────────
def main(mytimer: func.TimerRequest) -> None:
    logger = logging.getLogger("ConsolidatedReport")
    try:
        # Search
        search_ep = _cfg("SEARCH_ENDPOINT")
        search_key= _cfg("SEARCH_API_KEY")
        index     = _cfg("SEARCH_INDEX")

        # 리포트 설정
        top       = int(_cfg("STALE_TOP", "50"))
        days      = int(_cfg("DAYS_THRESHOLD", "180"))
        title     = _cfg("REPORT_TITLE", "DocSpace AI – Consolidated Report")
        container = _cfg("REPORTS_CONTAINER", "docspace-reports")
        teams_url = _cfg("TEAMS_WEBHOOK_URL", "")

        # 데이터 수집
        docs       = search_docs_top_oldest(search_ep, index, search_key, top)
        activities = fetch_recent_activity(limit=50)

        # MD 생성 & 저장
        md = build_markdown(docs, days, activities, title)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        blob_name = f"reports/consolidated-{ts}.md"
        full_name = save_blob_markdown(md, blob_name, container)

        # (선택) Teams 통지
        send_teams(teams_url, "DocSpace AI – Consolidated Saved",
                   f"Saved `{full_name}`  \nDocs sampled: **{len(docs)}**, Activities: **{len(activities)}**")

        logger.info(f"Saved consolidated report: {full_name}")
    except Exception as e:
        logger.exception(f"Consolidated report failed: {e}")
