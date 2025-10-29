
# compare.py – Similar-document comparator & merge suggestion via Azure OpenAI
from openai_client import azure_openai_chat

COMPARE_SYSTEM_PROMPT = """You are an expert documentation reviewer for Korean enterprise teams.
Given two documents A and B (in Korean), produce a concise Markdown report:
1) Summary of each document (2-3 bullets each).
2) Overlap & differences (bulleted).
3) Conflicts or contradictions with quotes.
4) Merge recommendation: which sections to keep from A vs B.
5) Draft a merged outline (H2/H3 headings) and 3 example sentences for critical areas.
Keep it actionable and compact.
"""

def generate_merge_report(doc_a_text: str, doc_b_text: str, title_a: str = "A", title_b: str = "B") -> str:
    user_prompt = f"""[문서 A: {title_a}]\n{doc_a_text[:8000]}\n\n[문서 B: {title_b}]\n{doc_b_text[:8000]}\n"""
    return azure_openai_chat([
        {"role":"system","content": COMPARE_SYSTEM_PROMPT},
        {"role":"user","content": user_prompt}
    ], temperature=0.1, max_tokens=1200)
