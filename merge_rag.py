# merge_rag.py
# RAG 기반 병합 문서 생성 + 저장 (local / blob / OneDrive)
import json, datetime as dt
from typing import List, Dict, Tuple
from config import CONFIG
from search import vector_search_by_text, vector_search, get_document_by_id
from storage_blob import upload_blob
from graph import upload_onedrive_file
import requests

# --- Azure OpenAI Chat 호출 (독립 REST) ---
def _aoai_chat(messages: List[Dict], max_tokens: int = 2000, temperature: float = 0.2) -> str:
    endpoint = CONFIG["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    api_key = CONFIG["AZURE_OPENAI_API_KEY"]
    deployment = CONFIG.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    api_versions = [
        "2025-01-01-preview",  # 최신 우선
        "2024-12-01-preview",
        "2024-08-01-preview",
        "2024-02-15-preview",
    ]
    last_err = None
    for ver in api_versions:
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={ver}"
        try:
            r = requests.post(
                url,
                headers={"Content-Type":"application/json","api-key":api_key},
                json={
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            last_err = r
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Azure OpenAI Chat 호출 실패: {last_err}")

# --- 유사 문서(또는 청크) 검색 ---
def retrieve_similar_contexts(base_text: str, k: int = 5, use_vector: bool = True) -> List[Dict]:
    """
    base_text와 유사한 문서 상위 k개를 조회하고 content까지 로드.
    index에 content 필드가 있어야 함.
    """
    if use_vector:
        hits = vector_search(base_text, k=k).get("value", [])
        ids = [h["id"] for h in hits]
    else:
        hits = vector_search_by_text(base_text, k=k)
        ids = [h["id"] for h in hits]

    contexts = []
    for _id in ids:
        doc = get_document_by_id(_id)
        if not doc:
            continue
        contexts.append({
            "id": doc.get("id"),
            "name": doc.get("name"),
            "content": doc.get("content", ""),
            "lastModified": doc.get("lastModified")
        })
    return contexts

# --- 병합 프롬프트 생성 ---
def _build_merge_prompt(doc_title: str, base_text: str, contexts: List[Dict]) -> List[Dict]:
    context_blocks = []
    for i, c in enumerate(contexts, 1):
        name = c.get("name") or c.get("id")
        txt = (c.get("content") or "")[:4000]  # 토큰 관리
        context_blocks.append(f"[#{i}] {name}\n{txt}")

    system = (
        "You are a senior technical editor. Merge documents into one coherent Korean document.\n"
        "- Remove ambiguities, ensure consistency, avoid passive voice.\n"
        "- Keep structure: 제목/요약/본론(섹션별)/결론/체크리스트.\n"
        "- Add citations like [#n] where the idea comes from the references.\n"
        "- If conflicts exist, resolve by choosing the latest or more precise rule and note it briefly."
    )
    user = f"""
[문서 제목]
{doc_title}

[기준 문서 본문]
{base_text[:8000]}

[참고 문서/단락 (인용용)]
{chr(10).join(context_blocks)}

[요구사항]
- 한국어 결과물(Markdown)
- 섹션 구조: # 제목 → ## 요약 → ## 본문(섹션별) → ## 결론 → ## 체크리스트
- 각 근거에 [#n] 인용 첨부
- 중복/충돌 사항은 '통합 규칙'으로 정리
"""
    return [
        {"role":"system", "content":system},
        {"role":"user", "content":user}
    ]

# --- 병합 문서 생성 (Markdown) ---
def generate_merged_markdown(doc_title: str, base_text: str, k: int = 5, use_vector: bool = True) -> Tuple[str, List[Dict]]:
    """
    반환: (merged_markdown, used_contexts)
    """
    contexts = retrieve_similar_contexts(base_text, k=k, use_vector=use_vector)
    messages = _build_merge_prompt(doc_title, base_text, contexts)
    merged_md = _aoai_chat(messages, max_tokens=2800, temperature=0.2)
    return merged_md, contexts

# --- 저장 유틸 ---
def save_merged(markdown: str, filename: str, target: str = "local") -> Dict:
    """
    target: 'local' | 'blob' | 'onedrive'
    - local: bytes 반환만 (상위 앱에서 download_button 사용)
    - blob : REPORTS_CONTAINER/docspace-merged/{filename}
    - onedrive: /DocSpaceAI/Merged/{filename}
    """
    b = markdown.encode("utf-8")

    if target == "local":
        return {"ok": True, "where": "local", "data": b}

    if target == "blob":
        # 컨테이너 내부 경로 Prefix
        path = f"docspace-merged/{filename}"
        upload_blob(path, b, overwrite=True, content_type="text/markdown")
        return {"ok": True, "where": "blob", "path": path}

    if target == "onedrive":
        # 폴더 경로 및 업로드
        folder = "DocSpaceAI/Merged"
        upload_onedrive_file(f"{folder}/{filename}", b)
        return {"ok": True, "where": "onedrive", "path": f"{folder}/{filename}"}

    return {"ok": False, "error": f"unknown target: {target}"}

# --- 편의 함수: 타임스탬프 파일명 ---
def merged_filename(base_name: str) -> str:
    ts = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe = (base_name or "merged").replace("/", "_")
    if not safe.lower().endswith(".md"):
        safe += ".md"
    return f"{ts}-{safe}"
