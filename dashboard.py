# dashboard.py
import datetime as dt
from typing import Dict, List
from config import CONFIG

# Search & Logs
from search import get_index_doc_count, get_recent_documents, get_timeseries_counts
try:
    from storage_logs import query_recent
    _HAS_TABLE = True
except Exception:
    _HAS_TABLE = False

def get_metrics(session_state) -> Dict:
    """
    실데이터 기반 간단 메트릭:
    - docs_loaded: Search 인덱스 문서 수
    - audits_done: 최근 로그에서 OpenAI 감사 이벤트 수(없으면 0)
    - pii_hits: 세션/로그 기반 값(없으면 0)
    - dup_found: 벡터 검색/중복탐지 결과가 없다면 0
    """
    docs_loaded = 0
    try:
        docs_loaded = get_index_doc_count()
    except Exception:
        pass

    audits_done = 0
    if _HAS_TABLE:
        try:
            logs = query_recent(top=200, user_id="default")
            audits_done = sum(1 for x in logs if str(x.get("Source","")).lower() in ("openai","audit") or "감사" in str(x.get("Message","")))
        except Exception:
            pass
    else:
        # 세션에 활동 로그가 있으면 참조
        logs = (session_state.get("_activity") or [])
        audits_done = sum(1 for x in logs if str(x.get("source","")).lower() in ("openai","audit") or "감사" in str(x.get("message","")))

    pii_hits = session_state.get("_pii_hits", 0)  # 별도 저장 시 반영
    dup_found = session_state.get("_dup_found", 0)

    return {
        "docs_loaded": docs_loaded,
        "audits_done": audits_done,
        "pii_hits": pii_hits,
        "dup_found": dup_found
    }

def get_recent_docs(session_state) -> List[Dict]:
    """
    Search 인덱스 기준 최근 문서가 있으면 사용, 없으면 Blob 상세 목록 상위 20 사용
    """
    # 1) Cognitive Search
    try:
        recent = get_recent_documents(top=20)
        if recent:
            return recent
    except Exception:
        pass

    # 2) Blob (fallback)
    try:
        from storage_blob import list_blobs_detailed
        rows = list_blobs_detailed()
        # 최근순 정렬
        rows.sort(key=lambda x: x.get("last_modified") or "", reverse=True)
        # 표준화
        return [{
            "id": r["name"],
            "name": r["name"],
            "lastModified": r.get("last_modified"),
            "views": None
        } for r in rows[:20]]
    except Exception:
        pass

    return []

def get_activity_log(session_state, top: int = 50) -> List[Dict]:
    """
    Table Storage 있으면 거기서, 없으면 세션에서
    """
    if _HAS_TABLE:
        try:
            rows = query_recent(top=top, user_id="default")
            return [{
                "time": r.get("CreatedAt"),
                "source": r.get("Source"),
                "level": r.get("Level"),
                "message": r.get("Message")
            } for r in rows]
        except Exception:
            pass

    slogs = session_state.get("_activity") or []
    return [{"time": "-", "source": x.get("source"), "level": x.get("level"), "message": x.get("message")} for x in slogs[:top]]

def get_timeseries(session_state, days: int = 12) -> List[Dict]:
    """
    Search 인덱스 기반으로 최근 N일 문서 수 추이
    """
    try:
        return get_timeseries_counts(days=days)
    except Exception:
        # 실패 시 날자만 미리 만들어 0으로 채움
        today = dt.date.today()
        start = today - dt.timedelta(days=days-1)
        return [{"date": (start + dt.timedelta(days=i)).isoformat(), "docs": 0} for i in range(days)]
