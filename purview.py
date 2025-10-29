
# purview.py – Stubs & guidance for Microsoft Purview integration
# In production, consider:
# - Purview Information Protection: auto-labeling sensitive info (MIP labels)
# - Purview Data Map/Catalog: register OneDrive/SharePoint and run scans
# - DLP policies: block external sharing when sensitive label present

import streamlit as st

def show_purview_guidance():
    st.markdown("""
### Purview 연동 가이드 (요약)
1. **Information Protection 레이블** 정의 (예: 내부/기밀/극비).
2. **자동 라벨 규칙** 작성: 주민번호, 카드번호, API Key 등 조건에 매칭되면 레이블 적용.
3. **DLP 정책** 설정: 기밀 문서 외부 공유 차단, Teams/Email 유출 방지.
4. **스캔 소스 등록**: SharePoint/OneDrive를 Purview Catalog에 등록하여 지속 스캔.
5. **경고/인시던트 처리**: 정책 위반 시 관리자 알림 또는 자동 격리.

> PoC에서는 간이 PII 스캔 후 결과를 Purview 레이블 적용 대상 후보로 표기하는 흐름을 사용하세요.
""")

def apply_label_stub(document_id: str, label_name: str):
    # Placeholder: 실제로는 MIP SDK 또는 Graph/Compliance Center 통합이 필요
    return {"status":"stub", "doc": document_id, "label": label_name}
