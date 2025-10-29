# auth_code.py
import msal, streamlit as st
from config import CONFIG

def ensure_login_auth_code() -> bool:
    # 이미 로그인됨
    if st.session_state.get("graph_access_token"):
        return True

    tenant_id = CONFIG.get("TENANT_ID", "common").strip() or "common"
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    client_id = CONFIG["CLIENT_ID"]
    client_secret = CONFIG.get("CLIENT_SECRET")
    redirect_uri = CONFIG.get("REDIRECT_URI", "http://localhost:8501")
    scopes = CONFIG.get("SCOPES", ["User.Read", "Files.Read"])

    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority
    )

    # 쿼리 파라미터 처리 개선
    query_params = st.experimental_get_query_params()
    code = query_params.get("code", [None])[0]

    if not code:
        auth_url = app.get_authorization_request_url(
            scopes=scopes,
            redirect_uri=redirect_uri,
            prompt="select_account"
        )
        st.link_button("Microsoft 로그인", auth_url)
        return False

    try:
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=scopes,
            redirect_uri=redirect_uri
        )
        
        if "access_token" in result:
            _save_graph_token_to_session(result)
            st.experimental_set_query_params()  # URL에서 코드 제거
            st.rerun()  # 페이지 리프레시
            return True
        
        st.error(f"토큰 획득 실패: {result.get('error_description', '알 수 없는 오류')}")
        return False
        
    except Exception as e:
        st.error(f"인증 처리 중 오류 발생: {str(e)}")
        return False

def _save_graph_token_to_session(result: dict) -> None:
    st.session_state["graph_access_token"] = result["access_token"]
    idc = result.get("id_token_claims", {}) or {}
    st.session_state["graph_id_token_claims"] = idc
    st.session_state["graph_user_mail"] = idc.get("preferred_username") or idc.get("email")
    st.session_state["graph_user_displayname"] = idc.get("name")
