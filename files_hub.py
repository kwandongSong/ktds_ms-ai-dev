# files_hub.py (최종 교정본)
import math
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict, Tuple

from config import CONFIG
from utils import safe_text, safe_excerpt
from storage_blob import list_blobs_detailed, download_blob
from graph import list_onedrive_root, list_onedrive_children, download_onedrive_file
from docintel import extract_text_naive, extract_text_docintel
from storage_logs import log_activity
from search import ensure_search_ready, make_safe_key, upsert_documents_with_embeddings
from pii import scan_pii
from purview import apply_label_stub
from owners_registry import set_owner, get_owner

# ----------------------------
# 내부 유틸
# ----------------------------

def go(page_name: str):
    st.session_state["__page"] = page_name
    st.session_state.pop("_nav_to", None)
    st.rerun()

def _is_doc(name: str) -> bool:
    name = (name or "").lower()
    return name.endswith((".pdf", ".txt", ".md", ".docx", ".pptx", ".xlsx"))

def _extract_text(name: str, content: bytes, use_docintel: bool) -> str:
    if use_docintel:
        return extract_text_docintel(content, mime_type="application/octet-stream")
    return extract_text_naive(name, content)

def _paginate(items: List[Dict], page: int, page_size: int) -> Tuple[List[Dict], int]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], math.ceil(total / page_size) if page_size else 1

def _raw_id_of_row(r: Dict) -> str:
    """원본 ID: Blob이면 경로/파일명, OneDrive면 드라이브 아이템 id"""
    return r["id"] if r.get("source") == "onedrive" else r["name"]

def _search_id_of_row(r: Dict) -> str:
    """인덱스에서 사용하는 안전 id"""
    return make_safe_key(_raw_id_of_row(r))

# ----------------------------
# 데이터 소스별 목록 수집 (캐시)
# ----------------------------
@st.cache_data(ttl=60)
def _fetch_blob_listing(prefix: str = "") -> List[Dict]:
    rows = list_blobs_detailed(prefix=prefix)
    for r in rows:
        r["source"] = "blob"
        r["id"] = r["name"]        # 원본ID = 파일 경로/이름
        r["is_folder"] = False
    return rows

@st.cache_data(ttl=60)
def _fetch_onedrive_listing(folder_id: str = None) -> List[Dict]:
    items = list_onedrive_children(folder_id) if folder_id else list_onedrive_root()
    rows = []
    for it in items:
        rows.append({
            "id": it.get("id"),     # 원본ID = drive item id
            "name": it.get("name"),
            "size": it.get("size"),
            "content_type": "folder" if "folder" in it else it.get("file", {}).get("mimeType"),
            "last_modified": it.get("lastModifiedDateTime"),
            "source": "onedrive",
            "is_folder": "folder" in it
        })
    return rows

# ----------------------------
# 일괄 인덱싱/업서트
# ----------------------------
def _bulk_index(docs_meta: List[Dict], source: str, use_docintel: bool, batch: int = 10):
    ok_cnt, fail_cnt = 0, 0
    payload_batch = []
    for meta in docs_meta:
        # 폴더는 건너뜀
        if meta.get("is_folder"):
            continue

        try:
            if source == "blob":
                data = download_blob(meta["name"])
                name = meta["name"]; original_id = meta["name"]
                path = meta["name"]
            else:
                data = download_onedrive_file(meta["id"])
                name = meta["name"]; original_id = meta["id"]
                path = meta["id"]   # OneDrive는 id를 path 대용으로 보존

            text = _extract_text(name, data, use_docintel=use_docintel)

            payload_batch.append({
                # id는 원본ID를 집어넣고, upsert_documents 내부에서 안전키로 변환됨
                "id": original_id,
                "originalId": original_id,
                "name": name,
                "source": source,
                "path": path,
                "content": text,
                "lastModified": meta.get("last_modified") or datetime.utcnow().isoformat(),
                "views": 0,
            })

            if len(payload_batch) >= batch:
                pii = scan_pii(text)
                if pii and sum(len(v) for v in pii.values()) > 0:
                    # 임시: PII 발견 시 Confidential 라벨 스텁
                    try:
                        apply_label_stub(original_id, "Confidential")
                    except Exception:
                        pass
                upsert_documents_with_embeddings(payload_batch)
                ok_cnt += len(payload_batch)
                payload_batch.clear()
        except Exception as e:
            fail_cnt += 1
            log_activity(
                st.session_state.get("graph_user_mail","default"),
                "Index",
                "ERROR",
                f"bulk index fail: {meta.get('name')} · {e}"
            )

    if payload_batch:
        pii = scan_pii(text)
        if pii and sum(len(v) for v in pii.values()) > 0:
            # 임시: PII 발견 시 Confidential 라벨 스텁
            try:
                apply_label_stub(original_id, "Confidential")
            except Exception:
                pass
        upsert_documents_with_embeddings(payload_batch)
        ok_cnt += len(payload_batch)

    log_activity(
        st.session_state.get("graph_user_mail","default"),
        "Index",
        "INFO",
        f"bulk index done: ok={ok_cnt}, fail={fail_cnt}"
    )
    return ok_cnt, fail_cnt

# ----------------------------
# 행 내 액션 메뉴(햄버거) 처리
# ----------------------------
def _row_actions(row: Dict, use_docintel: bool, page_tag: str):
    """
    각 행 오른쪽의 '⋮' popover 내부에서 실행되는 버튼들.
    """
    name = row.get("name")
    source = row.get("source")
    rid = row.get("id")  # 원본ID

    def _download_and_extract():
        data = download_blob(name) if source == "blob" else download_onedrive_file(rid)
        text = _extract_text(name, data, use_docintel=use_docintel)
        return data, text

    # ID 가시화 (디버깅/확인용)
    original_id = _raw_id_of_row(row)
    index_id = _search_id_of_row(row)
    # st.text_input("originalId", value=original_id, key=f"ori_{page_tag}_{index_id}", disabled=True)
    # st.text_input("index id (search)", value=index_id, key=f"sid_{page_tag}_{index_id}", disabled=True)
    
    cur = get_owner(original_id)
    email_in = st.text_input("담당자 이메일", value=cur.get("email",""), key=f"ownermail_{page_tag}_{index_id}")
    phone_in = st.text_input("담당자 휴대폰", value=cur.get("phone",""), key=f"ownerphone_{page_tag}_{index_id}")
    if st.button("💾 담당자 저장", key=f"owner_save_{page_tag}_{index_id}"):
        try:
            saved = set_owner(original_id, email=email_in, phone=phone_in)
            st.success("담당자 저장 완료")
            st.caption(f"검증: RowKey={saved['_RowKey']} · Table={saved['_Table']}")
            st.caption(f"OriginalId={saved['OriginalId']} / Email={saved['Email']} / Phone={saved['Phone']}")
        except Exception as e:
            st.error(f"저장 실패: {e}")        

    # 미리보기
    if st.button("👁 미리보기", key=f"pv_{page_tag}_{index_id}"):
        try:
            _, text = _download_and_extract()
            st.code(safe_excerpt(text, 1000))
            log_activity(st.session_state.get("graph_user_mail","default"), "FilesHub", "INFO", f"preview: {name}")
        except Exception as e:
            st.error(f"미리보기 실패: {e}")

    # 문서 감사
    if st.button("🧾 문서 감사로 이동", key=f"audit_{page_tag}_{index_id}"):
        try:
            _, text = _download_and_extract()
            st.session_state["current_doc"] = {"name": name, "id": rid, "text": text}
            log_activity(st.session_state.get("graph_user_mail","default"), "FilesHub", "INFO", f"to Audit: {name}")
            go("🧾 문서 감사")   # ← 여기!
        except Exception as e:
            st.error(f"감사 이동 실패: {e}")

    # 유사 검색/병합
    if st.button("🗂 유사 검색/병합 가이드", key=f"cur_{page_tag}_{index_id}"):
        try:
            _, text = _download_and_extract()
            st.session_state["current_doc"] = {"name": name, "id": rid, "text": text}
            log_activity(st.session_state.get("graph_user_mail","default"), "FilesHub", "INFO", f"to Curation: {name}")
            go("🗂️ 유사 검색 / 병합 가이드")  # ← 여기!
        except Exception as e:
            st.error(f"가이드 이동 실패: {e}")

    # 업서트
    if st.button("⬆ 인덱스 업서트", key=f"up_{page_tag}_{index_id}"):
        try:
            _, text = _download_and_extract()
            payload = [{
                "id": original_id,            # 원본ID → upsert 내에서 안전키로 변환
                "originalId": original_id,
                "name": name,
                "source": source,
                "path": (row.get("name") if source == "blob" else row.get("id")),
                "content": text,
                "lastModified": row.get("last_modified") or datetime.utcnow().isoformat(),
                "views": 0
            }]
            upsert_documents_with_embeddings(payload)
            st.success("업서트 완료")
            log_activity(st.session_state.get("graph_user_mail","default"), "Search", "INFO", f"upsert: {name}")
        except Exception as e:
            st.error(f"업서트 실패: {e}")
            log_activity(st.session_state.get("graph_user_mail","default"), "Search", "ERROR", f"upsert fail: {name} · {e}")

# ----------------------------
# 메인 렌더
# ----------------------------
def render_files_hub():
    # 1) Search 인덱스 보장
    try:
        ensure_search_ready(create_if_missing=True)
    except Exception as e:
        st.error(f"Search 초기화 실패: {e}")
        return

    st.title("📁 DocSpace")
    st.caption("파일 목록을 표시하고, 각 행의 햄버거(⋮) 메뉴에서 바로 작업을 실행합니다.")

    source_default = CONFIG.get("STORAGE_MODE", "onedrive")
    source = st.radio("데이터 소스", ["blob", "onedrive"], index=0 if source_default == "blob" else 1, horizontal=True)

    use_docintel = st.toggle("Azure Document Intelligence OCR 사용(가능시)", value=False)

    # q = st.text_input("이름 필터", value="")
    # if q:
    #     q_low = q.lower()
    #     rows = [r for r in rows if q_low in (r.get("name","").lower())]

    # 2) 목록 자동 로딩
    with st.spinner("파일 목록 불러오는 중…"):
        if source == "blob":
            rows = _fetch_blob_listing()
        else:
            rows = _fetch_onedrive_listing()

    # 폴더 제외(표에서 노출 막기)
    rows = [r for r in rows if not r.get("is_folder")]

    # 문서형만 보기
    if st.checkbox("문서 확장자만 보기 (.pdf/.txt/.md/.docx/.pptx/.xlsx)", value=True):
        rows = [r for r in rows if _is_doc(r.get("name",""))]

    # 3) 최초 일괄 인덱싱
    if not st.session_state.get("_indexed_once"):
        st.info("아직 전체 파일 인덱싱을 수행하지 않았습니다. 아래 버튼으로 현재 목록(필터 결과)을 일괄 업서트할 수 있습니다.")
    c1, c2 = st.columns([1,3])
    with c1:
        if st.button("🚀 현재 목록 일괄 인덱싱/업서트"):
            metas = rows
            ok, fail = _bulk_index(metas, source=source, use_docintel=use_docintel)
            st.session_state["_indexed_once"] = True
            st.success(f"일괄 인덱싱 완료 · 성공 {ok} · 실패 {fail}")

    # 검색/필터
    page_size = st.selectbox("페이지 크기", [10, 20, 50, 100], index=1)
    page = st.session_state.get("_files_page", 1)

    # 페이지네이션
    page_total = 1
    if rows:
        if page < 1: page = 1
        subset, page_total = _paginate(rows, page, page_size)
    else:
        subset = []

    # ====== 테이블(가상) 렌더: 햄버거 메뉴 포함 ======
    if not subset:
        st.warning("표시할 항목이 없습니다.")
        return

    # 헤더
    st.markdown("""
    <div style="display:grid;grid-template-columns: 1fr 120px 200px 160px 90px;gap:8px;font-weight:600;">
      <div>이름</div><div>크기</div><div>수정시각</div><div style="text-align:right">액션</div>
    </div>
    <hr style="opacity:.2;margin:6px 0 12px 0"/>
    """, unsafe_allow_html=True)

    # 행들
    for r in subset:
        name = r.get("name") or "-"
        size = r.get("size") or "-"
        lmod = r.get("last_modified") or "-"
        page_tag = f"{page}"

        cols = st.columns([6, 2, 3, 1], gap="small")
        with cols[0]:
            st.write(name)
        with cols[1]:
            st.caption(f"{size/1024/1024:.1f} MB" if isinstance(size, (int, float)) else "-")
        with cols[2]:
            st.caption(lmod)
        # 햄버거 팝오버
        with cols[3]:
            with st.popover("⋮", use_container_width=True):
                st.markdown(f"**{name}**")
                _row_actions(r, use_docintel=use_docintel, page_tag=page_tag)


    # 페이지 컨트롤
    pc1, pc2, pc3 = st.columns([1,2,1])
    with pc1:
        if st.button("◀️ 이전"):
            if page > 1:
                st.session_state["_files_page"] = page - 1
                st.rerun()
    with pc2:
        st.caption(f"페이지 {page} / {page_total} · 총 {len(rows)}건")
    with pc3:
        if st.button("다음 ▶️"):
            if page < page_total:
                st.session_state["_files_page"] = page + 1
                st.rerun()

