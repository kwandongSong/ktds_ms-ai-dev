# ops_alerts.py
import textwrap
from datetime import datetime, timedelta
from typing import List, Dict

from teams import send_teams_message
from storage_logs import query_recent
from config import CONFIG
from owners_registry import get_owner
from notifier import notify_owner

# Search 보조: 오래된 문서 리포트 (DateTime 문자열 정렬 기반 – PoC)
import requests
def _search_hdr():
    return {"Content-Type":"application/json", "api-key": CONFIG["SEARCH_API_KEY"]}

def _search_ep(): return CONFIG["SEARCH_ENDPOINT"].rstrip("/")
def _search_idx(): return CONFIG["SEARCH_INDEX"]

def find_stale_docs_by_order(top: int = 50) -> List[Dict]:
    """lastModified 오름차순으로 정렬해 상위 N개 리턴 (정확한 날짜필터는 운영 시 DateTimeOffset 스키마 권장)"""
    url = f"{_search_ep()}/indexes('{_search_idx()}')/docs/search?api-version=2023-11-01"
    body = {
        "search": "*",
        "select": "id,originalId,name,lastModified,source,path",
        "top": top,
        "queryType": "simple",
        "orderby": "lastModified asc"
    }
    r = requests.post(url, headers=_search_hdr(), json=body, timeout=30)
    r.raise_for_status()
    return r.json().get("value", [])

# ─────────────────────────────────────────────────────
# 알림 본문 생성기
# ─────────────────────────────────────────────────────
def build_weekly_digest(state) -> str:
    """주간 요약(업로드/감사/PII/중복) – state는 st.session_state 예상"""
    metrics = {
        "docs_loaded": state.get("metrics_docs_loaded") or 0,
        "audits_done": state.get("metrics_audits_done") or 0,
        "pii_hits": state.get("metrics_pii_hits") or 0,
        "dup_found": state.get("metrics_dup_found") or 0,
    }
    recent = state.get("_activity") or []  # 세션 로컬 활동 로그(없으면 0)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    body = f"""
    **DocSpace AI – 주간 리포트 ({today})**

    • 업로드/로드 문서: **{metrics['docs_loaded']}**  
    • 감사 완료: **{metrics['audits_done']}**  
    • PII 감지 건수: **{metrics['pii_hits']}**  
    • 유사/중복 감지: **{metrics['dup_found']}**

    최근 세션 활동 로그(샘플): **{len(recent)}**건  
    상세 활동/지표는 대시보드를 확인하세요.
    """
    return textwrap.dedent(body).strip()

def build_security_alert(pii_summ: Dict[str, List[str]] | None, label: str = "Confidential") -> str:
    """PII 요약을 받아 보안 알림 본문 생성"""
    total = sum(len(v) for v in (pii_summ or {}).values())
    lines = []
    if pii_summ:
        for k, arr in pii_summ.items():
            if not arr: continue
            lines.append(f"- {k}: {len(arr)}건")
    detail = "\n".join(lines) if lines else "- (상세 없음)"

    body = f"""
    **DocSpace AI – 보안 알림 (민감정보 감지)**

    총 감지 건수: **{total}**

    유형별 집계:  
    {detail}

    조치 권고: 해당 문서에 **{label}** 레이블 적용 및 접근 권한 재점검
    """
    return textwrap.dedent(body).strip()

def build_stale_docs_alert(limit: int = 20) -> str:
    """오래된 문서 상위 N개 간단 리스트 알림"""
    items = find_stale_docs_by_order(top=limit)
    lines = []
    for it in items[:limit]:
        name = it.get("name")
        lm = it.get("lastModified")
        oid = it.get("originalId")
        lines.append(f"- {name} (`{lm}`) · id: `{oid}`")

    body = f"""
    **DocSpace AI – 오래된 문서 리포트 (상위 {limit})**

    아래 문서들이 오래된 순으로 상위 {limit}에 해당합니다.  
    정기 점검/아카이브/업데이트를 검토하세요.

    {chr(10).join(lines) if lines else "- (대상 없음)"}
    """
    return textwrap.dedent(body).strip()

def build_conflict_alert(doc_a: str, doc_b: str, verdict: str) -> str:
    """두 문서 비교 결과(상충 여부 판단 문자열 포함)를 받아 알림 본문 생성"""
    body = f"""
    **DocSpace AI – 내용 충돌 감지**

    비교 대상:  
    • 문서 A: `{doc_a[:80]}...`  
    • 문서 B: `{doc_b[:80]}...`

    **판단 요약:**  
    {verdict}

    권고: 상충 구간을 정리하고 단일 진실 소스(Single Source of Truth)로 병합하세요.
    """
    return textwrap.dedent(body).strip()

# ─────────────────────────────────────────────────────
# 전송 헬퍼
# ─────────────────────────────────────────────────────
def send_alert(title: str, body_md: str):
    """Teams 웹훅으로 전송 (기존 teams.send_teams_message 사용)"""
    return send_teams_message(title, body_md)

def quick_activity_digest(user_id: str = "default", top: int = 20) -> str:
    """Azure Table의 최근 활동 로그를 요약해 간단 알림 본문 생성"""
    logs = query_recent(top=top, user_id=user_id) or []
    lines = []
    for r in logs:
        t = r.get("CreatedAt")
        lv = r.get("Level")
        msg = r.get("Message")
        lines.append(f"- [{lv}] {t} · {msg}")
    body = f"""
    **DocSpace AI – 활동 로그 요약 (최근 {top})**

    {chr(10).join(lines) if lines else "- (로그 없음)"}
    """
    return textwrap.dedent(body).strip()

def alert_to_owner_for_document(original_id: str, title: str, body_md: str, channels: list[str], graph_access_token: str | None):
    """
    단일 문서 originalId 기준, 담당자 조회 후 지정 채널로 발송
    """
    owner = get_owner(original_id)
    return notify_owner(owner, channels, title, body_md, graph_access_token)

def bulk_alert_stale_docs_to_owners(limit: int, channels: list[str], graph_access_token: str | None):
    """
    오래된 문서 상위 N개를 각각의 담당자에게 개별 발송
    """
    items = find_stale_docs_by_order(top=limit)
    results = []
    for it in items[:limit]:
        oid = it.get("originalId") or ""
        name = it.get("name") or ""
        lm = it.get("lastModified") or ""
        if not oid:
            continue
        body = f"""**오래된 문서 알림**  
- 문서: {name}  
- ID: `{oid}`  
- 마지막 수정: `{lm}`

권고: 업데이트/아카이브 여부 검토 바랍니다.
"""
        res = alert_to_owner_for_document(
            oid,
            title="DocSpace AI – 오래된 문서 (담당자 알림)",
            body_md=body,
            channels=channels,
            graph_access_token=graph_access_token
        )
        results.append({"originalId": oid, "sent": res})
    return results