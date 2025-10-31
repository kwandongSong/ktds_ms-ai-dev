# reports.py
from __future__ import annotations
from datetime import datetime, timezone
import streamlit as st
from typing import Optional

from config import CONFIG
from dashboard import get_metrics, get_recent_docs, get_timeseries
from storage_logs import query_recent, log_activity
from storage_blob import upload_blob
from ops_alerts import (
    build_weekly_digest, build_security_alert, build_stale_docs_alert, quick_activity_digest
)
from openai_client import run_audit_with_azure_openai  # 이미 쓰시던 클라이언트


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def refine_with_openai(md: str) -> str:
    try:
        prompt = f"다음 보고서 초안을 간결한 임원용 요약으로 1페이지 분량 Markdown으로 정리해줘:\n\n{md}"
        return run_audit_with_azure_openai(prompt, doc_type="Executive Summary")
    except Exception:
        return md

def build_consolidated_markdown(
    include_weekly: bool = True,
    include_security: bool = True,
    include_stale: bool = True,
    include_activity: bool = True,
    stale_limit: int = 20,
    activity_top: int = 20,
    custom_title: Optional[str] = None,
) -> str:
    """세션/백엔드에서 얻을 수 있는 요약들을 모아 하나의 MD로 병합"""
    title = custom_title or f"DocSpace AI – Consolidated Report ({datetime.now().strftime('%Y-%m-%d')})"
    lines = [f"# {title}", "", f"_Generated at (UTC) {_utc_now_iso()}_", ""]

    # (A) 대시보드 간단 메트릭
    try:
        m = get_metrics(st.session_state)
        lines += [
            "## Overview Metrics",
            f"- Loaded Docs: **{m.get('docs_loaded',0)}**",
            f"- Audits Done: **{m.get('audits_done',0)}**",
            f"- PII Hits: **{m.get('pii_hits',0)}**",
            f"- Duplicates Found: **{m.get('dup_found',0)}**",
            ""
        ]
    except Exception:
        pass

    # (B) 최근 문서
    try:
        recent = get_recent_docs(st.session_state)[:10]
        if recent:
            lines.append("## Recent Documents (Top 10)")
            for r in recent:
                nm = r.get("name","-"); lm = r.get("lastModified","-"); src = r.get("source","-")
                lines.append(f"- **{nm}**  _(src: {src}, lastModified: {lm})_")
            lines.append("")
    except Exception:
        pass

    # (C) 주간 요약(내부 빌더)
    if include_weekly:
        try:
            lines.append("## Weekly Digest")
            lines.append(build_weekly_digest(st.session_state))
            lines.append("")
        except Exception:
            pass

    # (D) 보안/PII 요약 — 현재 세션의 최신 스캔 결과 반영
    if include_security:
        pii = st.session_state.get("pii_scan")
        if pii:
            try:
                lines.append("## Security / PII Summary")
                lines.append(build_security_alert(pii, label="Confidential"))
                lines.append("")
            except Exception:
                pass

    # (E) 오래된 문서 요약
    if include_stale:
        try:
            lines.append(f"## Stale Documents (Top {stale_limit})")
            lines.append(build_stale_docs_alert(limit=stale_limit))
            lines.append("")
        except Exception:
            pass

    # (F) 활동 로그 요약
    if include_activity:
        try:
            uid = st.session_state.get("graph_user_mail","default")
            lines.append(f"## Activity Digest (User: {uid})")
            lines.append(quick_activity_digest(user_id=uid, top=activity_top))
            lines.append("")
        except Exception:
            pass

    # (G) 현재 열어둔 문서 감사 결과(있다면)
    if "audit_report" in st.session_state:
        lines.append("## Current Audit Result (Latest)")
        lines.append(st.session_state["audit_report"])
        lines.append("")

    return refine_with_openai("\n".join(lines).strip() + "\n")

def save_consolidated_report_to_blob(markdown_text: str, file_name: Optional[str] = None) -> str:
    """
    Markdown 텍스트를 Blob 컨테이너에 저장하고 blob 경로(이름) 반환.
    """
    container = CONFIG.get("REPORTS_CONTAINER") or CONFIG.get("BLOB_CONTAINER")
    if not file_name:
        file_name = f"reports/consolidated-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    upload_blob(file_name, markdown_text.encode("utf-8"), content_type="text/markdown", container=container)
    log_activity(st.session_state.get("graph_user_mail","default"), "Reports", "INFO", f"Saved consolidated: {file_name}")
    return file_name
