# search.py
import os, requests, datetime as dt
from typing import List, Dict
from config import CONFIG
import json
import requests
import streamlit as st
import base64, re, requests, json
from openai_client import get_embeddings 

API_VERSIONS = [
    "2025-09-01",      # 최신 안정 (지원 시)
    "2024-07-01",      # 널리 지원되는 안정
    "2023-11-01"       # 구 환경 호환
    "2024-12-01-preview"
]

def _api_url(path: str, api_version: str) -> str:
    ep = _ep()
    return f"{ep}{path}?api-version={api_version}"

def _get_admin_headers():
    h = _hdr()
    # 방어적으로 content-type을 명시
    if "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    return h

def _try_get(url):
    r = requests.get(url, headers=_get_admin_headers(), timeout=30)
    return r

def _try_put(url, payload):
    r = requests.put(url, headers=_get_admin_headers(), data=json.dumps(payload), timeout=60)
    return r

def _raise_with_text(prefix: str, r: requests.Response):
    try:
        detail = r.json()
    except Exception:
        detail = r.text
    raise requests.HTTPError(f"{prefix} {r.status_code}: {detail}", response=r)

def _hdr():
    key = CONFIG.get("SEARCH_API_KEY")
    if not key:
        raise RuntimeError("SEARCH_API_KEY 누락")
    return {"Content-Type":"application/json", "api-key": key}

def _ep():
    ep = (CONFIG.get("SEARCH_ENDPOINT") or "").rstrip("/")
    if not ep.startswith("https://"):
        raise RuntimeError(f"SEARCH_ENDPOINT 형식 오류: {ep}")
    return ep

def _idx():
    idx = CONFIG.get("SEARCH_INDEX")
    if not idx:
        raise RuntimeError("SEARCH_INDEX 누락")
    return idx


SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_\-=]+$")

def make_safe_key(raw: str) -> str:
    if not raw:
        raise ValueError("empty key")
    if SAFE_KEY_RE.fullmatch(raw):
        return raw
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")

_CACHED_FIELDS = None
def ensure_search_ready(create_if_missing=True):
    idx = _idx()

    # 0) 먼저 서비스 살아있는지 /indexes (목록)로 확인
    last_err = None
    chosen_ver = None

    for ver in API_VERSIONS:
        # 목록
        r = _try_get(_api_url("/indexes", ver))
        if r.status_code == 200:
            chosen_ver = ver
            break
        last_err = r

    if not chosen_ver:
        _raise_with_text("[ensure_search_ready] list indexes failed for all versions.", last_err)

    # 1) 인덱스 조회 (슬래시 포맷 → 괄호 포맷 둘 다 시도)
    for ver in [chosen_ver]:
        # 슬래시 포맷
        r1 = _try_get(_api_url(f"/indexes/{idx}", ver))
        if r1.status_code == 200:
            global API_VERSION
            API_VERSION = ver
            return "ready"
        # 괄호 포맷
        r2 = _try_get(_api_url(f"/indexes('{idx}')", ver))
        if r2.status_code == 200:
            API_VERSION = ver
            return "ready"

        # 404면 생성 시도
        if (r1.status_code == 404 or r2.status_code == 404) and create_if_missing:
            API_VERSION = ver
            return create_index_if_missing()

        last_err = r1 if r1.status_code != 200 else r2

    _raise_with_text("[ensure_search_ready] index check failed.", last_err)

# def ensure_search_ready(create_if_missing: bool = True) -> str:
#     """
#     Search 서비스/인덱스에 접근 가능 여부 확인.
#     없으면 create_if_missing=True일 때 기본 스키마로 생성.
#     """
#     ep, idx = _ep(), _idx()
#     url = f"{ep}/indexes('{idx}')?api-version={API_VERSION}"
#     r = requests.get(url, headers=_hdr(), timeout=20)
#     if r.status_code == 200:
#         return "ready"

#     if r.status_code == 404:
#         if not create_if_missing:
#             raise requests.HTTPError(f"Index not found: {idx}", response=r)
#         # 생성 시도
#         create_index_if_missing()
#         return "created"

#     # 401/403/400 등은 그대로 보여주어 디버깅
#     try:
#         detail = r.json()
#     except Exception:
#         detail = r.text
#     raise requests.HTTPError(f"Search index check failed {r.status_code}: {detail}", response=r)


def get_index_schema_fields():
    global _CACHED_FIELDS
    if _CACHED_FIELDS:
        return _CACHED_FIELDS

    ensure_search_ready(True)
    ep, idx = _ep(), _idx()

    # 먼저 슬래시 포맷
    url1 = _api_url(f"/indexes/{idx}", API_VERSION)
    r = _try_get(url1)
    if r.status_code == 200:
        data = r.json()
        _CACHED_FIELDS = {f["name"] for f in data.get("fields", [])}
        return _CACHED_FIELDS

    # 실패 시 괄호 포맷
    url2 = _api_url(f"/indexes('{idx}')", API_VERSION)
    r = _try_get(url2)
    if r.status_code == 200:
        data = r.json()
        _CACHED_FIELDS = {f["name"] for f in data.get("fields", [])}
        return _CACHED_FIELDS

    _raise_with_text("[get_index_schema_fields] failed to fetch schema.", r)

# def get_index_schema_fields():
#     """현재 인덱스의 필드 이름 set (캐시)"""
#     global _CACHED_FIELDS
#     if _CACHED_FIELDS is not None:
#         return _CACHED_FIELDS

#     # 없으면 생성까지 포함해 보장
#     ensure_search_ready(create_if_missing=True)

#     ep, idx = _ep(), _idx()
#     url = f"{ep}/indexes('{idx}')?api-version={API_VERSION}"
#     r = requests.get(url, headers=_hdr(), timeout=20)
#     r.raise_for_status()
#     data = r.json()
#     _CACHED_FIELDS = {f["name"] for f in data.get("fields", [])}
#     return _CACHED_FIELDS




def _base_url():
    ep = CONFIG["SEARCH_ENDPOINT"].rstrip("/")
    idx = CONFIG["SEARCH_INDEX"]
    return f"{ep}/indexes('{idx}')/docs"

def get_index_doc_count() -> int:
    """
    인덱스의 전체 문서 수
    """
    url = f"{_base_url()}?api-version={API_VERSION}&search=*&$count=true&$top=0"
    r = requests.get(url, headers=_hdr(), timeout=30)
    r.raise_for_status()
    # $count=true일 때, count는 헤더가 아니라 본문 '@odata.count'에 들어옴
    data = r.json()
    return int(data.get("@odata.count", 0))

def get_recent_documents(top: int = 20) -> List[Dict]:
    """
    최근 수정 문서 상위 N개 (lastModified 필드 기준)
    인덱스에 lastModified(Edm.String or DateTimeOffset) 필드가 있어야 함.
    """
    url = f"{_base_url()}?api-version={API_VERSION}&search=*&$top={top}&$orderby=lastModified desc"
    r = requests.get(url, headers=_hdr(), timeout=30)
    r.raise_for_status()
    hits = r.json().get("value", [])
    # 표준화 컬럼
    rows = []
    for h in hits:
        rows.append({
            "id": h.get("id") or h.get("@search.action") or "",
            "name": h.get("name") or h.get("fileName") or "",
            "lastModified": h.get("lastModified"),
            "views": h.get("views", 0),
        })
    return rows

def get_timeseries_counts(days: int = 12) -> List[Dict]:
    """
    최근 N일 일자별 문서 건수(간단 집계).
    facet interval이 어려우면 클라이언트에서 상위 문서를 내려받아 day 단위로 그룹핑.
    """
    # 넉넉히 상위 1000건만 끌어와서 집계
    url = f"{_base_url()}?api-version={API_VERSION}&search=*&$top=1000&$orderby=lastModified desc&$select=id,lastModified"
    r = requests.get(url, headers=_hdr(), timeout=30)
    r.raise_for_status()
    vals = r.json().get("value", [])
    # day bucket
    buckets = {}
    today = dt.datetime.utcnow().date()
    start = today - dt.timedelta(days=days-1)

    for v in vals:
        lm = v.get("lastModified")
        if not lm:
            continue
        try:
            # ISO -> date
            day = dt.date.fromisoformat(lm[:10])
        except Exception:
            # 문자열인 경우 'YYYY-MM-DD' 앞 10자만 파싱
            try:
                day = dt.datetime.strptime(lm[:10], "%Y-%m-%d").date()
            except Exception:
                continue
        if day < start:
            continue
        buckets[day] = buckets.get(day, 0) + 1

    # 누락일 0 채우기
    out = []
    for i in range(days):
        d = start + dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "docs": buckets.get(d, 0)})
    return out



# --- Cognitive Search 인덱스 관리/업서트/벡터 검색 기능 복원 ---
def create_index_if_missing():
    idx = _idx()

    # 임베딩 차원
    try:
        dim = int(CONFIG["AZURE_OPENAI_EMBED_DIM"])
    except Exception:
        raise RuntimeError("CONFIG['AZURE_OPENAI_EMBED_DIM']를 정수로 설정하세요. 예: 1536")

    # 최신 스키마 (2024-07-01 및 2025-09-01에서 유효)
    payload = {
        "name": idx,
        "fields": [
            {"name":"id","type":"Edm.String","key":True,"filterable":True},
            {"name":"originalId","type":"Edm.String","filterable":True},
            {"name":"name","type":"Edm.String","searchable":True,"sortable":True},
            {"name":"source","type":"Edm.String","filterable":True},
            {"name":"path","type":"Edm.String","filterable":True},
            {"name":"content","type":"Edm.String","searchable":True},
            {
                "name": "contentVector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "dimensions": dim,
                # ⬇️ 바뀐 포인트: 필드에는 vectorSearchProfile 지정
                "vectorSearchProfile": "vdb-hnsw"
            },
            {"name":"lastModified","type":"Edm.String","filterable":True,"sortable":True},
            {"name":"views","type":"Edm.Int32","filterable":True,"sortable":True}
        ],
        # ⬇️ 바뀐 포인트: profiles + algorithms 구성
        "vectorSearch": {
            "profiles": [
                {"name": "vdb-hnsw", "algorithm": "hnsw"}
            ],
            "algorithms": [
                {"name": "hnsw", "kind": "hnsw"}
            ]
        }
    }

    # 조회로 존재 확인 (버전은 ensure_search_ready에서 골라둔 API_VERSION 사용)
    url_get = _api_url(f"/indexes('{idx}')", API_VERSION)
    g = _try_get(url_get)
    if g.status_code == 200:
        return "already exists"

    # 생성 (둘 다 시도: /indexes/{name} 와 /indexes('name'))
    url_put1 = _api_url(f"/indexes/{idx}", API_VERSION)
    r1 = _try_put(url_put1, payload)
    if r1.status_code in (200, 201):
        global _CACHED_FIELDS
        _CACHED_FIELDS = {f["name"] for f in payload["fields"]}
        return "created"

    url_put2 = _api_url(f"/indexes('{idx}')", API_VERSION)
    r2 = _try_put(url_put2, payload)
    if r2.status_code in (200, 201):
        _CACHED_FIELDS = {f["name"] for f in payload["fields"]}
        return "created"

    # 에러 상세
    try: d1 = r1.json()
    except Exception: d1 = r1.text
    try: d2 = r2.json()
    except Exception: d2 = r2.text
    raise requests.HTTPError(
        f"[create_index_if_missing] PUT failed. slash={r1.status_code}:{d1} | paren={r2.status_code}:{d2}",
        response=r2
    )

# def create_index_if_missing():
#     """기본 스키마로 인덱스 생성 (이미 있으면 no-op)"""
#     ep, idx = _ep(), _idx()
#     # 존재여부 확인
#     url_get = f"{ep}/indexes('{idx}')?api-version={API_VERSION}"
#     r = requests.get(url_get, headers=_hdr(), timeout=20)
#     if r.status_code == 200:
#         return "already exists"

#     # 생성
#     url_put = f"{ep}/indexes/{idx}?api-version={API_VERSION}"
#     payload = {
#         "name": idx,
#         "fields": [
#             {"name":"id","type":"Edm.String","key":True,"filterable":True},
#             {"name":"originalId","type":"Edm.String","filterable":True},
#             {"name":"name","type":"Edm.String","searchable":True,"sortable":True},
#             {"name":"source","type":"Edm.String","filterable":True},
#             {"name":"path","type":"Edm.String","filterable":True},
#             {"name":"content","type":"Edm.String","searchable":True},
#             {"name":"lastModified","type":"Edm.String","filterable":True,"sortable":True},
#             {"name":"views","type":"Edm.Int32","filterable":True,"sortable":True}
#         ]
#     }
#     r = requests.put(url_put, headers=_hdr(), data=json.dumps(payload), timeout=30)
#     r.raise_for_status()
#     # 새 스키마 캐시
#     global _CACHED_FIELDS
#     _CACHED_FIELDS = {f["name"] for f in payload["fields"]}
#     return "created"

# ---------- 업서트 ----------
# --- 업서트(텍스트만) ---
def upsert_documents(docs, allow_unsafe_keys=False):
    ep, idx = _ep(), _idx()
    fields = get_index_schema_fields()
    url = f"{ep}/indexes('{idx}')/docs/index?api-version={API_VERSION}"
    if allow_unsafe_keys: url += "&allowUnsafeKeys=true"

    value = []
    for d in docs:
        original = d.get("id") or d.get("name")
        safe_id = make_safe_key(original)
        filtered = {k:v for k,v in d.items() if k in fields and k!="id"}
        filtered["id"] = safe_id
        if "originalId" in fields: filtered.setdefault("originalId", original)
        value.append({"@search.action":"mergeOrUpload", **filtered})
    r = requests.post(url, headers=_hdr(), json={"value": value}, timeout=60)
    if r.status_code >= 400:
        raise requests.HTTPError(r.text, response=r)
    return r.json()
# def upsert_documents(docs, allow_unsafe_keys=False):
#     """
#     docs: [{id, name, content, lastModified, views, source?, path?, originalId? ...}]
#     - 현재 인덱스 스키마 조회 (없으면 생성)
#     - 존재하는 필드만 전송
#     - id는 안전키 변환, originalId에 원본 id 보존(스키마 있을 때)
#     """
#     # 스키마 확보(필드 캐시)
#     field_names = get_index_schema_fields()

#     ep, idx = _ep(), _idx()
#     url = f"{ep}/indexes('{idx}')/docs/index?api-version={API_VERSION}"
#     if allow_unsafe_keys:
#         url += "&allowUnsafeKeys=true"

#     value = []
#     for d in docs:
#         original = d.get("id") or d.get("name")
#         safe_id = make_safe_key(original)

#         filtered = {k: v for k, v in d.items() if k in field_names and k != "id"}
#         filtered["id"] = safe_id
#         if "originalId" in field_names:
#             filtered.setdefault("originalId", original)

#         value.append({"@search.action": "mergeOrUpload", **filtered})

#     r = requests.post(url, headers=_hdr(), json={"value": value}, timeout=60)
#     if r.status_code >= 400:
#         try:
#             detail = r.json()
#         except Exception:
#             detail = r.text
#         raise requests.HTTPError(f"Search upsert failed {r.status_code}: {detail}", response=r)
#     return r.json()


# --- 업서트(임베딩 포함) ---
def upsert_documents_with_embeddings(docs):
    """
    docs: [{id, name, content, ...}]  -> contentVector 채워 업서트
    """
    texts = [d.get("content","") for d in docs]
    vectors = get_embeddings(texts)  # 리스트[list[float]] 목록
    # 차원 검증 (로그/예외)
    expected = int(CONFIG["AZURE_OPENAI_EMBED_DIM"])
    for i, vec in enumerate(vectors):
        if len(vec) != expected:
            raise ValueError(
                f"임베딩 차원 불일치: expected={expected}, got={len(vec)} (doc idx={i}, id={docs[i].get('id')})"
            )
    enriched = []
    for d, vec in zip(docs, vectors):
        dd = dict(d)
        dd["contentVector"] = vec
        enriched.append(dd)
    return upsert_documents(enriched)

# def vector_search(query_text: str, k: int = 5):
#     """
#     단순 텍스트 검색 기반 벡터 검색 (Text 기반)
#     """
#     ep = CONFIG["SEARCH_ENDPOINT"].rstrip("/")
#     idx = CONFIG["SEARCH_INDEX"]
#     key = CONFIG["SEARCH_API_KEY"]

#     url = f"{ep}/indexes('{idx}')/docs/search?api-version=2023-11-01"
#     headers = {"Content-Type": "application/json", "api-key": key}
#     payload = {
#         "search": query_text,
#         "queryType": "simple",
#         "top": k,
#         "select": "id,name,lastModified,views",
#     }
#     r = requests.post(url, headers=headers, json=payload)
#     if r.status_code != 200:
#         st.error(f"벡터 검색 실패: {r.text}")
#         return []
#     data = r.json().get("value", [])
#     return [{"id": d.get("id"), "name": d.get("name"), "score": d.get("@search.score")} for d in data]
# --- 벡터 검색 ---
def vector_search(query_text: str, k: int = 5):
    qvec = get_embeddings([query_text])[0]
    ep, idx = _ep(), _idx()
    url = f"{ep}/indexes('{idx}')/docs/search?api-version={API_VERSION}"
    body = {
      "count": True,
      "select": "id,originalId,name,source,path,lastModified",
      "vectorQueries": [
        {"kind":"vector", "vector": qvec, "exhaustive": False, "k": k, "fields": "contentVector"}
      ]
    }
    r = requests.post(url, headers=_hdr(), json=body, timeout=60)
    if r.status_code >= 400:
        try: st.error(f"[vector_search] {r.status_code} {r.text}")
        except Exception: pass
        r.raise_for_status()
    return r.json()

def show_search_guidance(st_container=None):
    """
    Search 인덱스 및 벡터 검색 가이드 표시용 (Streamlit UI)
    """
    c = st_container or st
    c.markdown("### 🔍 Cognitive Search 가이드")
    c.markdown("""
    **DocSpace AI**는 Azure Cognitive Search를 이용해 문서를 인덱싱하고 검색합니다.  

    **주요 함수**
    - `create_index_if_missing()` : 인덱스 존재 확인 및 자동 생성
    - `upsert_documents(docs)` : 문서 인덱스에 업서트
    - `vector_search(query_text, k)` : 벡터/텍스트 검색

    인덱스 필드 예시:
    ```
    id (key) | name | content | lastModified | views
    ```
    """)

def get_document_by_id(doc_id: str) -> dict:
    """
    인덱스에서 특정 id의 문서 단건 조회 (content 포함)
    """
    ep = CONFIG["SEARCH_ENDPOINT"].rstrip("/")
    idx = CONFIG["SEARCH_INDEX"]
    url = f"{ep}/indexes('{idx}')/docs?api-version={API_VERSION}&$filter=id eq '{doc_id}'&$top=1"
    r = requests.get(url, headers=_hdr(), timeout=30)
    r.raise_for_status()
    vals = r.json().get("value", [])
    return vals[0] if vals else {}

def vector_search_by_text(text: str, k: int = 5, select: str = "id,name,lastModified,views") -> List[Dict]:
    """
    텍스트를 그대로 쿼리해 상위 k개 유사 문서를 반환
    (벡터/하이브리드 구성 전 PoC용 simple search)
    """
    ep = CONFIG["SEARCH_ENDPOINT"].rstrip("/")
    idx = CONFIG["SEARCH_INDEX"]
    url = f"{ep}/indexes('{idx}')/docs/search?api-version={API_VERSION}"
    payload = {"search": text[:3000], "queryType": "simple", "top": k, "select": select}
    r = requests.post(url, headers=_hdr(), json=payload, timeout=30)
    r.raise_for_status()
    vals = r.json().get("value", [])
    # 정규화
    out = []
    for v in vals:
        out.append({
            "id": v.get("id"),
            "name": v.get("name"),
            "lastModified": v.get("lastModified"),
            "views": v.get("views"),
            "score": v.get("@search.score"),
        })
    return out
