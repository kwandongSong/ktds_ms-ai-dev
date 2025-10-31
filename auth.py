# auth.py
import msal, streamlit as st
from config import CONFIG

def ensure_login() -> bool:
    tenant_id = CONFIG.get("TENANT_ID", "common").strip() or "common"
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    client_id = CONFIG["CLIENT_ID"]
    scopes = CONFIG.get("SCOPES", ["User.Read", "Files.Read","Mail.Send"])

    app = msal.PublicClientApplication(client_id=client_id, authority=authority)

    # silent first
    accts = app.get_accounts()
    if accts:
        result = app.acquire_token_silent(scopes=scopes, account=accts[0])
        if result and "access_token" in result:
            _save_graph_token_to_session(result)
            return True

    # device code flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        st.error("Device Code Flow 시작 실패")
        return False
    st.info(f"브라우저에서 **{flow['verification_uri']}** 접속 후 코드 입력: **{flow['user_code']}**")
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        _save_graph_token_to_session(result)
        st.success("로그인 성공 (Device Code)")
        return True

    st.error(result.get("error_description", "로그인 실패"))
    return False

def _save_graph_token_to_session(result: dict) -> None:
    st.session_state["graph_access_token"] = result["access_token"]
    idc = result.get("id_token_claims", {}) or {}
    st.session_state["graph_id_token_claims"] = idc
    st.session_state["graph_user_mail"] = idc.get("preferred_username") or idc.get("email")
    st.session_state["graph_user_displayname"] = idc.get("name")
