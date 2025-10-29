
# openai_client.py
import requests
from config import CONFIG

API_VERSION = "2024-10-21"

def azure_openai_chat(messages, temperature: float = 0.2, max_tokens: int = 800) -> str:
    url = f"{CONFIG['AZURE_OPENAI_ENDPOINT']}/openai/deployments/{CONFIG['AZURE_OPENAI_DEPLOYMENT']}/chat/completions?api-version=2025-01-01-preview"
    headers = {
        "api-key": CONFIG["AZURE_OPENAI_API_KEY"],
        "Content-Type": "application/json"
    }
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def azure_openai_embed(text: str, embedding_deployment: str = "text-embedding-3-large"):
    url = f"{CONFIG['AZURE_OPENAI_ENDPOINT']}/openai/deployments/{embedding_deployment}/embeddings?api-version=2025-01-01-preview"
    headers = {"api-key": CONFIG["AZURE_OPENAI_API_KEY"], "Content-Type": "application/json"}
    payload = {"input": text}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["data"][0]["embedding"]

AUDIT_SYSTEM_PROMPT = """You are an expert Korean technical editor and requirements auditor. 
Analyze the provided document in Korean. 
1) Find ambiguous phrases and explain why. 
2) Identify potential conflicts/contradictions. 
3) Suggest missing sections based on the provided doc type. 
4) Propose concrete line-edits (active voice, concise style) as bullet points.
Return a concise Markdown report in Korean.
"""

def run_audit_with_azure_openai(doc_text: str, doc_type: str) -> str:
    user_prompt = f"""[문서 유형]: {doc_type}
[문서 본문]:
{doc_text[:12000]}
"""
    return azure_openai_chat([
        {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ])


def _aoai_url(deployment: str) -> str:
    ep = CONFIG["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    return f"{ep}/openai/deployments/{deployment}/chat/completions?api-version={API_VERSION}"

def _aoai_headers():
    return {
        "api-key": CONFIG["AZURE_OPENAI_API_KEY"],
        "Content-Type": "application/json",
    }

def run_audit_with_azure_openai(text: str, doc_type: str) -> str:
    """
    (기존) 감사 리포트 생성 함수가 이미 있다면 유지하세요.
    이건 예시 시그니처입니다.
    """
    url = _aoai_url(CONFIG["AZURE_OPENAI_DEPLOYMENT"])
    body = {
        "messages": [
            {"role": "system", "content": f"You are an expert reviewer for {doc_type}."},
            {"role": "user", "content": f"다음 문서를 검토하고 모호성/충돌/누락을 조목조목 지적해줘.\n\n{text}"}
        ],
        "temperature": 0.2,
    }
    r = requests.post(url, headers=_aoai_headers(), json=body, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def refine_document_with_azure_openai(original_text: str,
                                      audit_report: str,
                                      tone: str = "formal",
                                      length: str = "concise",
                                      output_format: str = "markdown") -> str:
    """
    감사 결과(audit_report)를 반영해 원문을 재작성.
    output_format: markdown | plain | rst 등 (MD 권장)
    """
    url = _aoai_url(CONFIG["AZURE_OPENAI_DEPLOYMENT"])
    sys = (
        "You are a senior technical editor. "
        "Rewrite the document by FIXING issues referenced in the audit report. "
        "Preserve factual content; remove ambiguity; align style with an engineering style guide; "
        "ensure consistency; add missing must-have sections if the audit suggests them."
    )
    usr = (
        f"[Constraints]\n"
        f"- Tone: {tone}\n- Length preference: {length}\n- Output format: {output_format}\n\n"
        f"[Audit Report]\n{audit_report}\n\n[Original Document]\n{original_text}"
    )
    body = {
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": usr}
        ],
        "temperature": 0.2,
    }
    r = requests.post(url, headers=_aoai_headers(), json=body, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]