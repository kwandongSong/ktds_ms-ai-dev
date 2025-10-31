# login_page.py
import streamlit as st
from auth_code import ensure_login_auth_code

# 세션 키 통일
_TOK = "graph_access_token"
_REF = "graph_refresh_token"

def is_logged_in():
    """로그인 상태 확인 (토큰 존재 여부)"""
    return bool(st.session_state.get("graph_access_token"))


def do_logout():
    # 세션 토큰/프로필 비우고 URL 파라미터 정리
    for k in (_TOK, _REF, "graph_user_displayname", "graph_user_mail", "graph_user_upn"):
        if k in st.session_state:
            del st.session_state[k]
    # st.query_params 사용 (experimental_* 금지)
    qp = st.query_params
    cleared = {k: None for k in ("code", "state", "session_state", "error", "error_description") if k in qp}
    if cleared:
        st.query_params = {k: v for k, v in qp.items() if k not in cleared}

def render_login_page(default_next: str = "📊 대시보드"):
    st.title("🔐 DocSpace AI 로그인")
    st.caption("Microsoft Entra(Office 365) 계정으로 로그인하세요.")

    # 아직 미로그인 → 로그인 링크 노출 (auth_code.ensure_login_auth_code 내부에서 링크 렌더)
    ok = ensure_login_auth_code()

    if not ok:
        st.info("로그인이 필요합니다. 위 링크를 클릭해 권한 동의를 완료하세요.")
        st.markdown("---")
        st.caption("문제가 있나요? 브라우저 팝업/시크릿 모드, 테넌트/앱 등록 설정을 확인하세요.")
        return

    # 로그인 완료 UI
    user = st.session_state.get("graph_user_displayname") or "사용자"
    mail = st.session_state.get("graph_user_mail") or "(메일 정보 없음)"

    st.success("로그인 완료")
    st.markdown(
        f"""
        <div style="border:1px solid #2a2a2a33;border-radius:14px;padding:16px;background:rgba(255,255,255,0.03)">
          <h3 style="margin:0">{user}</h3>
          <div style="opacity:.8">{mail}</div>
          <div style="margin-top:8px">
            <span style="display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #1f6feb55;margin-right:6px;font-size:12px">Graph</span>
            <span style="display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #1f6feb55;margin-right:6px;font-size:12px">Azure OpenAI</span>
            <span style="display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #1f6feb55;margin-right:6px;font-size:12px">Blob/Search</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("➡️ 계속하기"):
            st.session_state["_nav_to"] = default_next
            st.rerun()
    with c2:
        if st.button("🚪 로그아웃"):
            do_logout()
            st.rerun()
