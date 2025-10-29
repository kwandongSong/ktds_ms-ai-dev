# utils.py
import streamlit as st
import base64

def config_status(CONFIG):
    st.markdown("### 🔧 설정 상태")
    st.write({
        "Azure OpenAI": bool(CONFIG.get("AZURE_OPENAI_API_KEY")),
        "Cognitive Search": bool(CONFIG.get("SEARCH_API_KEY")),
        "Document Intelligence": bool(CONFIG.get("AI_DOC_INTEL_KEY")),
        "Graph/Entra": bool(CONFIG.get("TENANT_ID") and CONFIG.get("CLIENT_ID")),
        "Storage Mode": CONFIG.get("STORAGE_MODE", "onedrive"),
        "Blob(Account)": CONFIG.get("AZURE_STORAGE_ACCOUNT", ""),
        "Blob(Container)": CONFIG.get("AZURE_STORAGE_CONTAINER", ""),
    })

def log_event(source: str, message: str, level: str = "info"):
    arr = st.session_state.get("_activity", [])
    arr.insert(0, {"source": source, "message": message, "level": level})
    st.session_state["_activity"] = arr[:200]

def safe_text(obj, default: str = "") -> str:
    """임의 객체를 안전한 str로 변환 (Ellipsis/bytes/None 방지)"""
    if obj is None:
        return default
    if obj is Ellipsis:  # '...' (Ellipsis) 보호
        return default
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return default
    return str(obj)

def safe_excerpt(obj, limit: int = 900, default: str = "") -> str:
    s = safe_text(obj, default=default)
    return s[:limit]


def make_key(s: str) -> str:
    # URL-safe Base64 ( -,_ 만 사용 ), 패딩 '=' 제거해도 됨
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")