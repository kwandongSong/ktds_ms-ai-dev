# app.py – Streamlit main (Sidebar Navigation + Dashboard)
import streamlit as st
import pandas as pd
from datetime import datetime

from config import CONFIG
from utils import config_status, safe_excerpt, safe_text, make_key
from auth import ensure_login
from auth_code import ensure_login_auth_code
from graph import list_onedrive_root, list_onedrive_children, download_onedrive_file, upload_onedrive_file
from docintel import extract_text_naive, extract_text_docintel
from openai_client import run_audit_with_azure_openai, refine_document_with_azure_openai
from pii import scan_pii
from teams import send_teams_message
from purview import show_purview_guidance, apply_label_stub
from dashboard import get_metrics, get_recent_docs, get_activity_log, get_timeseries
from storage_logs import query_recent, ensure_table, log_activity
from storage_blob import upload_blob, download_blob, delete_blob, list_blobs_detailed
from search import (
    show_search_guidance, create_index_if_missing, upsert_documents, vector_search,
    get_document_by_id, vector_search_by_text, get_recent_documents
)
from compare import generate_merge_report
from login_page import render_login_page, is_logged_in  
from files_hub import render_files_hub  # ← 추가

try:
    ensure_table()
except Exception:
    pass

st.set_page_config(page_title="DocSpace AI (Azure PoC)", page_icon="🧠", layout="wide")

st.markdown("""
<style>
.metric-row {display:flex; gap:16px; flex-wrap:wrap; margin: 8px 0 16px 0;}
.card {border:1px solid #2a2a2a33; border-radius:14px; padding:16px; background: rgba(255,255,255,0.03);}
.pill {display:inline-block; padding:4px 10px; border-radius:999px; background:#1f6feb22; border:1px solid #1f6feb55; margin-right:6px; font-size:12px;}
.ok {color:#2ecc71;} .warn {color:#f39c12;}
</style>
""", unsafe_allow_html=True)

# ----------------------------
# Router Guard: 로그인 페이지가 첫 화면
# ----------------------------
# 첫 진입이거나 세션 만료 시 → 로그인 페이지 렌더하고 종료
# 로그인 페이지 렌더링 전에 상태 체크
if not is_logged_in():
    render_login_page(default_next="📁 파일 허브")
    st.stop()

# ----------------------------
# Sidebar & Navigation (로그인 이후에만 보임)
# ----------------------------
NAV_KEY = "__page"
PAGES = [
    "📁 파일 허브",
    "📊 대시보드",
    "🔐 Space",
    "🧾 문서 감사",
    "🗂️ 지식 정리/보안",
    "🔔 알림/운영",
]

def go(page_name: str):
    """프로그램적으로 페이지 이동"""
    st.session_state[NAV_KEY] = page_name
    # 과거 잔여 네비 변수 사용 금지
    st.session_state.pop("_nav_to", None)
    st.rerun()

def current_page() -> str:
    """현재 페이지 얻기 (기본은 파일 허브)"""
    return st.session_state.get(NAV_KEY, "📁 파일 허브")

# ─────────────────────────────────────────────────
# (사이드바 렌더 전) 과거에 쓰던 _nav_to를 발견하면 NAV_KEY로 승격
if "_nav_to" in st.session_state and st.session_state["_nav_to"] in PAGES:
    st.session_state[NAV_KEY] = st.session_state.pop("_nav_to")

# 사이드바
with st.sidebar:
    st.title("🧠 DocSpace AI")
    cur = current_page()
    # 라디오의 선택 초기값을 항상 현재 페이지로!
    idx = PAGES.index(cur)
    page = st.radio("NAVIGATION", PAGES, index=idx)
    if page != cur:
        # 사용자가 라디오로 직접 변경한 경우
        st.session_state[NAV_KEY] = page
        st.rerun()
# with st.sidebar:
#     st.title("🧠 DocSpace AI")
#     page = st.radio("NAVIGATION", PAGES, index=0)
#     if st.session_state.get("graph_access_token"):
#         who = st.session_state.get("graph_user_displayname") or st.session_state.get("graph_user_mail")
#         st.caption(f"🔓 Signed in: {who}")
#     else:
#         st.caption("🔒 Not signed in")
#     st.caption("Move fast. Keep docs clean.")


def render_dashboard():
    st.title("📊 대시보드 · Profile & Settings")
    col1, col2 = st.columns([2,1])

    with col1:
        st.subheader("프로필 / 세션")
        user_name = st.session_state.get("graph_user_displayname", "게스트")
        user_mail = st.session_state.get("graph_user_mail", "not signed in")
        st.markdown(f"""<div class="card"><h3 style="margin:0">{user_name}</h3>
        <div style="opacity:.8">{user_mail}</div>
        <div style="margin-top:8px">
            <span class="pill">OneDrive</span><span class="pill">Azure OpenAI</span>
            <span class="pill">Cognitive Search</span><span class="pill">Purview</span>
        </div></div>""", unsafe_allow_html=True)

    # ✅ 실데이터 메트릭
    metrics = get_metrics(st.session_state)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("업로드/로드 문서", metrics["docs_loaded"])
    m2.metric("감사 완료", metrics["audits_done"])
    m3.metric("PII 감지", metrics["pii_hits"])
    m4.metric("유사/중복 감지", metrics["dup_found"])

    # ✅ 실데이터 타임시리즈
    import altair as alt
    ts = get_timeseries(st.session_state, days=12)
    df_ts = pd.DataFrame(ts)
    chart = alt.Chart(df_ts).mark_area(opacity=0.6).encode(
        x="date:T", y="docs:Q", tooltip=["date","docs"]
    ).properties(height=220)
    st.altair_chart(chart, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("최근 문서")
        docs = get_recent_docs(st.session_state)
        st.dataframe(pd.DataFrame(docs), use_container_width=True, height=220)
    with c2:
        # st.subheader("활동 로그")
        # logs = get_activity_log(st.session_state, top=50)
        # st.dataframe(pd.DataFrame(logs), use_container_width=True, height=260)
        try:
            ensure_table()
        except Exception:
            pass
        st.subheader("활동 로그")
        use_cloud = st.toggle("Azure Table에서 불러오기", value=True)
        try:
            if use_cloud:
                logs = query_recent(top=50, user_id=st.session_state.get("graph_user_mail","default"))
                view = [{"time": x.get("CreatedAt"), "source": x.get("Source"),
                         "level": x.get("Level"), "message": x.get("Message")} for x in logs]
            else:
                slogs = st.session_state.get("_activity") or []
                view = [{"time": "-", **x} for x in slogs]
            st.dataframe(pd.DataFrame(view), use_container_width=True, height=260)
        except Exception as e:
            st.warning(f"로그 조회 실패: {e}")

    with col2:
        st.subheader("설정 상태")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        config_status(CONFIG)
        st.markdown('</div>', unsafe_allow_html=True)

def render_storage():
    st.title("🔐 로그인 & 저장소")

    configured_mode = CONFIG.get("STORAGE_MODE", "onedrive").lower()
    st.caption(f"현재 설정된 저장소 모드: **{configured_mode}**")
    mode = st.radio("저장소 모드 선택 (임시 전환용)", ["onedrive", "blob"],
                    index=0 if configured_mode == "onedrive" else 1, horizontal=True)

    login_method = st.radio("로그인 방식", ["Device Code Flow", "Auth Code Flow"], horizontal=True)
    if not st.session_state.get("graph_access_token"):
        if login_method == "Device Code Flow":
            if not ensure_login():
                st.stop()
        else:
            if not ensure_login_auth_code():
                st.stop()
    st.success(f"Graph 토큰 확보됨 · 사용자: {st.session_state.get('graph_user_displayname') or st.session_state.get('graph_user_mail')}")

    # 프로필 뱃지
    user_name = st.session_state.get("graph_user_displayname") or st.session_state.get("graph_user_mail") or "signed-in"
    st.success(f"✅ 로그인됨: {user_name}")

    if mode == "onedrive":
        st.subheader("📁 OneDrive")
        try:
            root = list_onedrive_root()
            log_activity("default", "OneDrive", "INFO", "로그인 성공 및 토큰 확보")
        except Exception as e:
            st.warning("OneDrive 사용이 불가합니다. Blob 저장소를 사용해주세요.")
            st.exception(e)
            st.info("상단에서 'blob' 모드로 전환하세요.")
            return

        df = pd.DataFrame([{"name": it.get("name"), "id": it.get("id"), "isFolder": ("folder" in it)} for it in root])
        st.subheader("루트 항목")
        st.dataframe(df, use_container_width=True, height=300)

        sel_label = ["-"] + [f"{r['name']} ({r['id'][:8]})" for r in root]
        sel = st.selectbox("항목 선택", sel_label)
        chosen = None
        if sel != "-":
            chosen_id_prefix = sel.split("(")[-1].strip(")")
            chosen = next((r for r in root if r["id"].startswith(chosen_id_prefix)), None)

        if chosen and ("folder" in chosen):
            st.info("폴더 내용 불러오는 중…")
            try:
                children = list_onedrive_children(chosen["id"])
                cdf = pd.DataFrame([{"name": it.get("name"), "id": it.get("id"), "isFolder": ("folder" in it)} for it in children])
                st.dataframe(cdf, use_container_width=True, height=300)
            except Exception as e:
                st.error("폴더 목록 조회 실패")
                st.exception(e)

        if chosen and ("folder" not in chosen):
            use_docintel = st.checkbox("Azure Document Intelligence로 텍스트 추출", value=False)
            if st.button("이 파일 가져오기 & 텍스트 추출"):
                try:
                    content = download_onedrive_file(chosen["id"])
                    text = extract_text_docintel(content, mime_type="application/octet-stream") if use_docintel \
                           else extract_text_naive(chosen["name"], content)
                    st.session_state["current_doc"] = {"name": chosen["name"], "id": chosen["id"], "text": safe_text(text, "")}
                    st.success(f"{chosen['name']} 파일을 세션에 로드했습니다.")
                    try:
                        log_activity("default", "OneDrive", "INFO", f"파일 로드 및 텍스트 추출: {chosen['name']}")
                    except Exception: pass
                except Exception as e:
                    st.error("파일 다운로드/추출 실패")
                    st.exception(e)

        if st.session_state.get("current_doc"):
            st.markdown("**현재 문서 미리보기 (상위 900자):**")
            text_preview = safe_excerpt(st.session_state.get("current_doc", {}).get("text"), 900)
            st.code(text_preview)
        return

    # blob mode
    st.subheader("📦 Azure Blob Storage")
    uploaded = st.file_uploader("문서 업로드", type=["pdf","docx","txt","md","pptx","xlsx"])
    if uploaded:
        try:
            upload_blob(uploaded.name, uploaded.getvalue(), content_type=uploaded.type)
            st.success(f"✅ 업로드 완료: {uploaded.name}")
            try:
                log_activity("default", "Blob", "INFO", f"업로드 완료: {uploaded.name}")
            except Exception: pass
        except Exception as e:
            st.error("업로드 실패"); st.exception(e)
            try:
                log_activity("default", "Blob", "ERROR", f"업로드 실패: {uploaded.name} · {e}")
            except Exception: pass

    if st.button("컨테이너 목록 조회"):
        try:
            files = list_blobs_detailed()
            if not files:
                st.info("컨테이너가 비어 있습니다.")
            else:
                df = pd.DataFrame(files)
                st.dataframe(df, use_container_width=True, height=300)
            log_activity("default", "Blob", "INFO", f"목록 조회: {len(files)}건")
        except Exception as e:
            st.error("목록 조회 실패"); st.exception(e)
            log_activity("default", "Blob", "ERROR", f"목록 조회 실패: {e}")

    col_dl, col_rm = st.columns(2)
    with col_dl:
        name = st.text_input("다운로드/텍스트추출 파일명", placeholder="예: document.pdf")
        use_docintel = st.checkbox("Azure Document Intelligence로 텍스트 추출", value=False, key="blob_docintel")
        if st.button("다운로드 & (선택) 추출"):
            try:
                data = download_blob(name)
                text = (
                    extract_text_docintel(data, mime_type="application/octet-stream")
                    if use_docintel
                    else extract_text_naive(name, data)
                )
                st.session_state["current_doc"] = {"name": name, "id": name, "text": safe_text(text, "")}
                st.success(f"{name} 파일을 세션에 로드했습니다.")
                st.download_button("💾 원본 파일 저장", data, file_name=name)
                try:
                    log_activity("default", "Blob", "INFO", f"다운로드 & 추출: {name}")
                except Exception: pass
            except Exception as e:
                st.error("다운로드/추출 실패"); st.exception(e)
                try:
                    log_activity("default", "Blob", "ERROR", f"다운로드/추출 실패: {name} · {e}")
                except Exception: pass

    with col_rm:
        del_name = st.text_input("삭제할 파일명", placeholder="예: old.txt")
        if st.button("파일 삭제"):
            try:
                delete_blob(del_name)
                st.success(f"🗑️ 삭제 완료: {del_name}")
                try:
                    log_activity("default", "Blob", "WARN", f"파일 삭제: {del_name}")
                except Exception: pass
            except Exception as e:
                st.error("삭제 실패"); st.exception(e)
                try:
                    log_activity("default", "Blob", "ERROR", f"삭제 실패: {del_name} · {e}")
                except Exception: pass

    if st.session_state.get("current_doc"):
        st.markdown("**현재 문서 미리보기 (상위 900자):**")
        text_preview = safe_excerpt(st.session_state.get("current_doc", {}).get("text"), 900)
        st.code(text_preview)

def render_audit():
    st.title("🧾 문서 감사")
    col1, col2 = st.columns([3,2])
    with col1:
        doc_type = st.selectbox("문서 유형", ["요구사항 명세서", "프로젝트 계획서", "기술 설계서", "기타"])
        default_text = safe_text(st.session_state.get("current_doc", {}).get("text"), "")
        text = st.text_area("문서 본문 (자동 입력/수정 가능)", value=default_text, height=320)
        
        if st.button("Azure OpenAI로 감사 실행"):
            if not text.strip():
                st.warning("본문을 입력하거나 저장소에서 파일을 가져오세요.")
            else:
                try:
                    with st.spinner("Azure OpenAI 분석 중…"):
                        report = run_audit_with_azure_openai(text, doc_type)
                    st.session_state["audit_report"] = report
                    st.success("분석 완료")
                    try:
                        log_activity("default", "OpenAI", "INFO", f"감사 실행 완료 · 유형={doc_type}")
                    except Exception: pass
                except Exception as e:
                    st.error(f"OpenAI 호출 실패: {e}")
                    try:
                        log_activity("default", "OpenAI", "ERROR", f"감사 실행 실패 · {e}")
                    except Exception: pass

        st.markdown("##### PII 간이 스캔 (PoC)")
        if st.button("PII 스캔 실행"):
            result = scan_pii(text)
            st.session_state["pii_scan"] = result
            try:
                count = sum(len(v) for v in (result or {}).values())
                level = "WARN" if count > 0 else "INFO"
                log_activity("default", "PII", level, f"PII 스캔 결과 · 항목수={count}")
            except Exception: pass

    with col2:
        st.markdown("#### 분석 결과")
        if "audit_report" in st.session_state:
            st.markdown(st.session_state["audit_report"])
            st.download_button("리포트 저장 (Markdown)", st.session_state["audit_report"].encode("utf-8"), file_name="audit_report.md")
        if "pii_scan" in st.session_state:
            pii = st.session_state["pii_scan"]
            if pii:
                st.warning("민감정보 의심 항목 요약:")
                for k, arr in pii.items():
                    st.write(f"- {k}: {len(arr)}개")
            else:
                st.info("민감정보 패턴이 발견되지 않았습니다.")

    st.markdown("---")
    st.markdown("### 📄 감사 결과 반영 재작성 · 파일 생성/저장")

    current_text = st.session_state.get("current_doc", {}).get("text", "")
    audit_md = st.session_state.get("audit_report", "")
    if not current_text:
        st.info("현재 문서가 비어 있습니다. 저장소에서 문서를 먼저 불러오세요.")
    if not audit_md:
        st.info("감사 리포트가 없습니다. 위에서 'Azure OpenAI로 감사 실행'을 먼저 수행하세요.")

    colL, colR = st.columns([3,2])
    with colL:
        tone = st.selectbox("톤", ["formal", "neutral", "friendly"], index=0)
        length = st.selectbox("길이 선호", ["concise", "balanced", "detailed"], index=1)
        out_fmt = st.selectbox("출력 포맷", ["markdown", "plain"], index=0)

        default_name = (st.session_state.get("current_doc", {}).get("name") or "document") \
                        .rsplit(".", 1)[0] + "-refined.md"
        file_name = st.text_input("생성 파일명", value=default_name)

        target_store = st.radio("저장소", ["auto (CONFIG)", "onedrive", "blob"], horizontal=True)
        if target_store.startswith("auto"):
            target_store = CONFIG.get("STORAGE_MODE", "onedrive")

        if st.button("🤖 문서 재작성 실행"):
            if not current_text or not audit_md:
                st.warning("현재 문서 또는 감사 리포트가 없습니다.")
            else:
                try:
                    with st.spinner("재작성 중…"):
                        refined = refine_document_with_azure_openai(
                            original_text=current_text,
                            audit_report=audit_md,
                            tone=tone, length=length, output_format=out_fmt
                        )
                    st.session_state["refined_text"] = refined
                    st.success("재작성 완료")
                    log_activity("default", "OpenAI", "INFO", "문서 재작성 완료")
                except Exception as e:
                    st.error(f"재작성 실패: {e}")

    with colR:
        st.markdown("#### 미리보기")
        if "refined_text" in st.session_state:
            st.code(st.session_state["refined_text"][:1200], language="markdown")
            st.download_button("💾 로컬로 저장 (MD)", st.session_state["refined_text"].encode("utf-8"), file_name=file_name)

            # 저장 버튼
            if st.button("☁️ 클라우드로 저장"):
                try:
                    bytes_out = st.session_state["refined_text"].encode("utf-8")
                    if target_store == "blob":
                        upload_blob(file_name, bytes_out, overwrite=True, content_type="text/markdown")
                        st.success(f"Blob에 저장됨: {file_name}")
                        log_activity("default", "Blob", "INFO", f"재작성 문서 저장: {file_name}")
                    else:
                        # onedrive (폴더 경로 포함하고 싶다면 'DocSpace/refined/...' 형태를 권장)
                        path = f"DocSpace/refined/{file_name}"
                        upload_onedrive_file(path, bytes_out, conflict_behavior="replace", mime="text/markdown")
                        st.success(f"OneDrive에 저장됨: {path}")
                        log_activity("default", "OneDrive", "INFO", f"재작성 문서 저장: {path}")
                except Exception as e:
                    log_activity("default", target_store.capitalize(), "ERROR", f"재작성 문서 저장 실패: {e}")
                    st.error(f"저장 실패: {e}")

    # st.markdown("---")
    # st.markdown("### 유사 문서 비교 · 병합 제안")
    # base_text = st.session_state.get("current_doc", {}).get("text", "")
    # a = st.text_area("문서 A (비교 대상)", value=base_text[:800], height=160)
    # b = st.text_area("문서 B (비교 대상)", height=160, placeholder="다른 문서를 붙여넣어 비교하세요.")
    # if st.button("OpenAI로 비교/병합 리포트 생성"):
    #     if not a.strip() or not b.strip():
    #         st.warning("두 문서 본문을 입력하세요.")
    #     else:
    #         with st.spinner("비교 분석 중…"):
    #             cmp_report = generate_merge_report(a, b, title_a="A", title_b="B")
    #         st.markdown(cmp_report)
    #         st.download_button("리포트 저장 (Markdown)", cmp_report.encode("utf-8"), file_name="merge_report.md")

def render_curation():
    st.title("🗂️ 지식 정리/보안")
    st.markdown("#### 1) 인덱스 생성")
    if st.button("인덱스 생성/확인"):
        try:
            res = create_index_if_missing()
            st.success(f"인덱스 상태: {res}")
            try: log_activity("default", "Search", "INFO", f"인덱스 상태: {res}")
            except Exception: pass
        except Exception as e:
            st.error(f"인덱스 생성 실패: {e}")
            try: log_activity("default", "Search", "ERROR", f"인덱스 생성 실패: {e}")
            except Exception: pass

    st.markdown("#### 2) 현재 문서를 인덱스에 업서트")
    if st.button("현재 문서 업서트"):
        doc = st.session_state.get("current_doc")
        if not doc:
            st.warning("먼저 저장소에서 문서를 불러오세요.")
        else:
            try:
                payload = [{
                    "id": make_key(doc["id"]),
                    "name": doc["name"],
                    "content": doc["text"],
                    "lastModified": datetime.utcnow().isoformat(),
                    "views": 0
                }]
                res = upsert_documents(payload)
                st.success("업서트 완료")
                st.json(res)
                log_activity("default", "Search", "INFO", f"업서트 완료: {doc['name']}")
            except Exception as e:
                st.error(f"업서트 실패: {e}")

    st.markdown("#### 3) 벡터 검색 (유사 문서 찾기)")
    q = st.text_input("쿼리 텍스트", value=st.session_state.get("current_doc",{}).get("text","")[:500])
    if st.button("벡터 검색 실행"):
        try:
            results = vector_search(q, k=5)
            st.write(results)
            try:
                log_activity("default", "Search", "INFO", f"벡터 검색 · 질의 길이={len(q)} · 결과={len(results)}")
            except Exception: pass
        except Exception as e:
            st.error(f"벡터 검색 실패: {e}")
            try:
                log_activity("default", "Search", "ERROR", f"벡터 검색 실패: {e}")
            except Exception: pass

    
    st.markdown("---")
    st.header("🔎 유사 문서 탐색 & 병합 가이드")

    # 1) 기준 문서 선택: (A) 현재 문서 or (B) 인덱스 목록에서 선택
    base_mode = st.radio("기준 문서 선택", ["현재 문서", "인덱스에서 선택"], horizontal=True)

    base_doc = None
    base_text = None

    if base_mode == "현재 문서":
        base_doc = st.session_state.get("current_doc")
        if not base_doc:
            st.info("현재 문서가 없습니다. 저장소 탭에서 문서를 불러오거나, 아래 '인덱스에서 선택'을 이용하세요.")
        else:
            base_text = safe_text(base_doc.get("content"), "")
            st.success(f"기준: {base_doc.get('name')} (세션)")
    else:
        # 최근 문서 목록에서 선택
        try:
            recents = get_recent_documents(top=30)
        except Exception:
            recents = []
        if not recents:
            st.warning("인덱스에서 최근 문서를 불러오지 못했습니다. 먼저 문서를 업서트 해보세요.")
        else:
            labels = [f"{d['name']}  ·  {d.get('lastModified','')}" for d in recents]
            idx = st.selectbox("기준 문서를 선택하세요", options=list(range(len(recents))), format_func=lambda i: labels[i])
            chosen = recents[idx]
            base_doc = {"id": chosen["id"], "name": chosen["name"]}
            # 인덱스에서 content를 함께 가져옴
            detail = get_document_by_id(chosen["id"])
            base_text = detail.get("content", "")
            if base_text:
                st.success(f"기준: {chosen['name']} (인덱스)")
            else:
                st.warning("선택 문서에 content 필드가 없거나 비어 있습니다.")

    # 2) 유사 문서 리스트 (상위 k개)
    st.subheader("상위 유사 문서")
    top_k = st.slider("개수", min_value=3, max_value=15, value=5, step=1)
    similar = []
    if base_text:
        try:
            with st.spinner("유사 문서 검색 중…"):
                similar = vector_search_by_text(base_text, k=top_k)
                log_activity("default", "Search", "INFO", f"유사 문서 후보 {len(similar)}건")
        except Exception as e:
            st.error(f"유사 문서 검색 실패: {e}")

    if similar:
        import pandas as pd
        df_sim = pd.DataFrame(similar)
        st.dataframe(df_sim, use_container_width=True, height=240)

        # 3) 후보 중 하나 선택 → 어떤 점이 유사한지 & 병합 가이드
        st.markdown("#### 비교 대상 선택")
        option_labels = [f"{d['name']} (score={d.get('score'):.3f})" for d in similar]
        sel_idx = st.selectbox("비교/병합 가이드를 볼 문서", options=list(range(len(similar))), format_func=lambda i: option_labels[i])
        target_meta = similar[sel_idx]
        # 선택 문서 내용 로드
        target_detail = get_document_by_id(target_meta["id"])
        target_text = target_detail.get("content", "")

        # UI: 왜 유사한지 간단 근거 (키워드 겹침)
        st.markdown("#### 왜 유사할까요? (간이 근거)")
        def _top_terms(t, n=15):
            import re, collections
            toks = re.findall(r"[A-Za-z가-힣0-9_]{2,}", (t or "").lower())
            stop = set(["the","and","for","with","that","this","from","are","was","were","into","have","has","as","of","in","to","a","an","or","on","by","at","be","is","it","및","그리고","으로","에서","에게","하다","된다","수","등"])
            toks = [x for x in toks if x not in stop]
            cnt = collections.Counter(toks)
            return [w for w,_ in cnt.most_common(n)]

        if base_text and target_text:
            base_terms = set(_top_terms(base_text, 40))
            target_terms = set(_top_terms(target_text, 40))
            overlap = sorted(list(base_terms & target_terms))[:20]
            st.write({"공통 키워드(샘플)": overlap})

        st.markdown("#### 병합 제안 리포트")
        if st.button("OpenAI로 병합 가이드 생성"):
            try:
                with st.spinner("분석 중…"):
                    report_md = generate_merge_report(
                        base_text or "",
                        target_text or "",
                        title_a=base_doc.get("name","Base"),
                        title_b=target_meta.get("name","Candidate")
                    )
                st.session_state["merge_report_md"] = report_md
                st.success("가이드 생성 완료")
                log_activity("default", "OpenAI", "INFO", f"병합 가이드 생성 · 기준={base_doc.get('name','Base')} · 대상={target_meta.get('name')}")
            except Exception as e:
                st.error(f"병합 가이드 생성 실패: {e}")

        if st.session_state.get("merge_report_md"):
            st.markdown(st.session_state["merge_report_md"])
            st.download_button(
                "💾 병합 가이드 저장 (Markdown)",
                st.session_state["merge_report_md"].encode("utf-8"),
                file_name="merge_guidance.md"
            )
    else:
        if base_text:
            st.info("유사 문서가 충분히 나오지 않았습니다. 인덱스에 더 많은 문서를 업서트 해보세요.")

    show_search_guidance(st)
    st.markdown("#### Purview 연동 가이드")
    show_purview_guidance()
    label_target = st.text_input("라벨 적용 대상 문서 ID (Stub)", value=st.session_state.get("current_doc",{}).get("id",""))
    label_name = st.text_input("라벨 이름 (Stub)", value="Confidential")
    if st.button("라벨 적용 (Stub)"):
        res = apply_label_stub(label_target, label_name)
        st.json(res)

def render_ops():
    st.title("🔔 알림/운영")
    title = st.text_input("알림 제목", "DocSpace AI – 리포트 알림")
    body = st.text_area("알림 본문", "중복/노후/PII 감지 결과 요약을 전달합니다.")
    if st.button("Teams 웹훅으로 전송"):
        try:
            res = send_teams_message(title, body)
            st.success("전송 완료")
        except Exception as e:
            st.error(f"전송 실패: {e}")
    st.markdown("---")
    st.caption("Logic Apps 템플릿(주간 리포트)은 logicapps_samples/ 에 있습니다.")

if st.session_state.get("_nav_to") in PAGES:
    page = st.session_state.pop("_nav_to")

if page == "📁 파일 허브":
    render_files_hub()
elif page == "📊 대시보드":
    render_dashboard()
elif page == "🔐 로그인 & 저장소":
    render_storage()
elif page == "🧾 문서 감사":
    render_audit()
elif page == "🗂️ 지식 정리/보안":
    render_curation()
elif page == "🔔 알림/운영":
    render_ops()
else:
    render_files_hub()

st.markdown("---")
st.caption("© 2025 DocSpace AI – Azure Integrated Prototype (Sidebar Navigation).")

