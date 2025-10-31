# graph.py
import requests, streamlit as st
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

def _token() -> str:
    tok = st.session_state.get("graph_access_token")
    if isinstance(tok, dict):
        tok = tok.get("access_token")
    if not tok:
        raise RuntimeError("Graph access token not found. 로그인 먼저 진행하세요.")
    return tok

def _headers():
    return {"Authorization": f"Bearer {_token()}", "Accept": "application/json"}

def _raise_with_detail(r: requests.Response, context: str):
    try:
        detail = r.json()
        msg = (detail.get("error") or {}).get("message") or r.text
    except Exception:
        detail, msg = {"text": r.text}, r.text

    if "Tenant does not have a SPO license" in msg:
        st.error("이 테넌트에는 SharePoint Online 라이선스가 없어 OneDrive API를 사용할 수 없습니다.")
        st.info("해결: 1) SPO 라이선스 부여 2) 사용자 OneDrive 첫 진입(프로비저닝) 후 재시도")
    else:
        st.warning(f"[Graph {context}] {r.status_code} {r.reason}\n\n{detail}")
    r.raise_for_status()

def list_onedrive_root():
    r = requests.get(f"{GRAPH_BASE}/me/drive", headers=_headers(), timeout=30)
    if r.status_code >= 400: _raise_with_detail(r, "GET /me/drive")
    r2 = requests.get(f"{GRAPH_BASE}/me/drive/root/children", headers=_headers(), timeout=30)
    if r2.status_code >= 400: _raise_with_detail(r2, "GET /me/drive/root/children")
    return r2.json().get("value", [])

def list_onedrive_children(item_id: str):
    r = requests.get(f"{GRAPH_BASE}/me/drive/items/{item_id}/children", headers=_headers(), timeout=30)
    if r.status_code >= 400: _raise_with_detail(r, f"GET /me/drive/items/{item_id}/children")
    return r.json().get("value", [])

def download_onedrive_file(item_id: str) -> bytes:
    r = requests.get(f"{GRAPH_BASE}/me/drive/items/{item_id}/content", headers=_headers(), timeout=60)
    if r.status_code >= 400: _raise_with_detail(r, f"GET /me/drive/items/{item_id}/content")
    return r.content

# graph.py (맨 아래에 추가)
# def upload_onedrive_file(path_name: str, content: bytes, conflict_behavior: str = "replace", mime: str = "text/markdown"):
#     """
#     path_name 예: 'DocSpace/refined/mydoc-refined.md'
#     conflict_behavior: 'replace' | 'rename' | 'fail'
#     """
#     headers = _headers()
#     headers["Content-Type"] = mime
#     url = (f"{GRAPH_BASE}/me/drive/root:/{path_name}:/content"
#            f"?@microsoft.graph.conflictBehavior={conflict_behavior}")
#     r = requests.put(url, headers=headers, data=content, timeout=90)
#     if r.status_code >= 400:
#         _raise_with_detail(r, f"PUT /me/drive/root:/{path_name}:/content")
#     return r.json()  # 업로드된 item 메타데이터


def upload_onedrive_file(path: str, data: bytes, mime: str = "text/markdown"):
    """
    /me/drive/root:/path:/content 로 업로드 (없으면 생성/덮어쓰기)
    path 예: DocSpaceAI/Merged/2025-10-31-merged.md
    """
    url = f"{GRAPH_BASE}/me/drive/root:/{path}:/content"
    r = requests.put(
        url,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": mime},
        data=data,
        timeout=60
    )
    if r.status_code not in (200, 201):
        raise requests.HTTPError(f"OneDrive 업로드 실패 {r.status_code}: {r.text}", response=r)
    return r.json()