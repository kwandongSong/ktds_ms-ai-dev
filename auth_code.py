# auth_code.py
import time, requests, msal, streamlit as st
from config import CONFIG

GRAPH_ME = "https://graph.microsoft.com/v1.0/me"

def _client():
    return msal.ConfidentialClientApplication(
        client_id=CONFIG["CLIENT_ID"],
        client_credential=CONFIG["CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{CONFIG['TENANT_ID']}"
    )

def _save_profile_from_graph(access_token: str):
    """/me 호출해서 세션에 이름/메일 저장. mail이 비면 userPrincipalName으로 대체."""
    r = requests.get(GRAPH_ME, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    r.raise_for_status()
    me = r.json()
    display = me.get("displayName") or me.get("givenName") or me.get("userPrincipalName") or "User"
    mail = me.get("mail") or me.get("userPrincipalName") or me.get("id")  # mail이 빈 경우 많음
    st.session_state["graph_user_displayname"] = display
    st.session_state["graph_user_mail"] = mail
    # 원하는 다른 필드도 보관 가능
    st.session_state["graph_user_id"] = me.get("id")


def ensure_login_auth_code() -> bool:
    # 토큰 재사용 (만료 60초 전이면 갱신 시도)
    tok = st.session_state.get("graph_access_token")
    exp = st.session_state.get("graph_access_token_expires_at", 0)
    if tok and time.time() < exp - 60:
        # 프로필이 없다면 한 번만 채움
        if not st.session_state.get("graph_user_displayname"):
            try: _save_profile_from_graph(tok)
            except Exception: pass
        return True

    # 콜백 code 처리
    code = st.query_params.get("code")
    if code:
        app = _client()
        res = app.acquire_token_by_authorization_code(
            code=code,
            scopes=CONFIG["SCOPES"],  # ["openid","profile","offline_access","User.Read","Mail.Send"]
            redirect_uri=CONFIG["REDIRECT_URI"]
        )
        if "access_token" in res:
            st.session_state["graph_access_token"] = res["access_token"]
            st.session_state["graph_refresh_token"] = res.get("refresh_token")  # 있으면 저장
            st.session_state["graph_access_token_expires_at"] = time.time() + int(res.get("expires_in", 3600))
            # 프로필 저장
            try: _save_profile_from_graph(res["access_token"])
            except Exception as e: st.warning(f"프로필 로딩 실패: {e}")
            # code 제거(재사용 방지)
            st.query_params.clear()
            return True
        else:
            st.error(f"토큰 획득 실패: {res.get('error_description')}")
            return False

    # 만료 시 refresh_token으로 재발급 (있을 때)
    rt = st.session_state.get("graph_refresh_token")
    if rt:
        app = _client()
        res = app.acquire_token_by_refresh_token(rt, scopes=CONFIG["SCOPES"])
        if "access_token" in res:
            st.session_state["graph_access_token"] = res["access_token"]
            st.session_state["graph_refresh_token"] = res.get("refresh_token", rt)
            st.session_state["graph_access_token_expires_at"] = time.time() + int(res.get("expires_in", 3600))
            try: _save_profile_from_graph(res["access_token"])
            except Exception: pass
            return True

    # 로그인 링크 노출
    app = _client()
    auth_url = app.get_authorization_request_url(
        scopes=CONFIG["SCOPES"],
        redirect_uri=CONFIG["REDIRECT_URI"],
        prompt="select_account"
    )
    st.link_button("Microsoft 로그인", auth_url, use_container_width=True)
    return False


# def ensure_login_auth_code() -> bool:
#     # 이미 로그인됨
#     if st.session_state.get("graph_access_token"):
#         return True

#     tenant_id = CONFIG.get("TENANT_ID", "common").strip() or "common"
#     authority = f"https://login.microsoftonline.com/{tenant_id}"
#     client_id = CONFIG["CLIENT_ID"]
#     client_secret = CONFIG.get("CLIENT_SECRET")
#     redirect_uri = CONFIG.get("REDIRECT_URI", "http://localhost:8501")
#     scopes = CONFIG.get("SCOPES", ["User.Read", "Files.Read", "Mail.Send"])

#     app = msal.ConfidentialClientApplication(
#         client_id=client_id,
#         client_credential=client_secret,
#         authority=authority
#     )

#     # 쿼리 파라미터 처리 개선
#     query_params = st.experimental_get_query_params()
#     code = query_params.get("code", [None])[0]

#     if not code:
#         auth_url = app.get_authorization_request_url(
#             scopes=scopes,
#             redirect_uri=redirect_uri,
#             prompt="select_account"
#         )
#         st.link_button("Microsoft 로그인", auth_url)
#         return False

#     try:
#         result = app.acquire_token_by_authorization_code(
#             code=code,
#             scopes=scopes,
#             redirect_uri=redirect_uri
#         )
        
#         if "access_token" in result:
#             _save_graph_token_to_session(result)
#             st.experimental_set_query_params()  # URL에서 코드 제거
#             st.rerun()  # 페이지 리프레시
#             return True
        
#         st.error(f"토큰 획득 실패: {result.get('error_description', '알 수 없는 오류')}")
#         return False
        
#     except Exception as e:
#         st.error(f"인증 처리 중 오류 발생: {str(e)}")
#         return False

def _save_graph_token_to_session(result: dict) -> None:
    st.session_state["graph_access_token"] = result["access_token"]
    idc = result.get("id_token_claims", {}) or {}
    st.session_state["graph_id_token_claims"] = idc
    st.session_state["graph_user_mail"] = idc.get("preferred_username") or idc.get("email")
    st.session_state["graph_user_displayname"] = idc.get("name")
