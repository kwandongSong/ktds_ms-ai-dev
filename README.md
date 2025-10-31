링크 : https://kwand-wepapp-1030.azurewebsites.net/
계정 : ktds7_14@modulabsbiz.onmicrosoft.com

# 🧠 DocSpace AI — Azure 기반 문서 인텔리전스 허브

**MVP Project**  
>
Works Space,Drive 시스템의 m365 전환 대비 m365 라인업 제품군들과의 연동 및 AI 접목 고도화
문서 색인, 유사 문서 탐색, 민감정보 탐지 및 자동 보고 기능을 갖춘 AI 문서 관리 플랫폼

---

## 📘 개요

**DocSpace AI**는 조직 내 문서 자산을 색인화하고,  
유사도 분석 및 GPT 기반 감사 기능을 통해  
문서 관리의 정확도·효율성을 높이는 **AI 문서 감사 솔루션**입니다.

> 정형/비정형 문서 → 텍스트 추출 → 임베딩 → 벡터 검색 → 감사/알림  
> 까지 전 과정을 Azure 환경내 구현

---

## 🏗️ 시스템 아키텍처

<img width="1132" height="692" alt="image" src="https://github.com/user-attachments/assets/51e7a7bb-06e6-461d-96c2-b52b8a017b2e" />


---

## ☁️ Azure 리소스 구성 요약

| 영역 | 리소스명 | 역할 | 비고 |
|------|-----------|------|------|
| **AI Search** | Azure AI Search | 문서 인덱싱 + 벡터 검색 | `contentVector` 필드 사용 |
| **AI Model** | Azure OpenAI | GPT-4o-mini/ text-embedding-3-small | 의미 비교·요약·임베딩 |
| **OCR** | Azure Document intelligence| 비정형 문서 텍스트 추출, OCR처리 | 전처리 활용 |
| **App Service** | Streamlit Web App | 사용자 UI + 관리 콘솔 | Linux 환경 |
| **Storage** | Blob Storage | 문서 저장, 종합 리포트 저장 | `docspace`, `docspace-reports` |
|  | Table Storage | 담당자 / 로그 관리 | `DocspaceOwners`, `DocspaceActivity` |
| ~~**Functions**~~ | Python Timer Trigger | 정기 보고서 생성 (5분마다) | Storage Key 인증 |
| **Logic Apps / Graph API** | Teams / Outlook 알림 | 담당자별 자동 발송 | Mail.Send 권한 필요 |

---

## ⚙️ 주요 기능

| 기능 | 기술 구성 | 설명 |
|------|-------------|------|
| **문서 색인 및 검색** | AI Search + OpenAI Embeddings | 문서 내용 임베딩 후 인덱싱 → 벡터 기반 검색 |
| **유사 문서 감지** | Vector Search (HNSW) | Top-k 유사 문서 탐색으로 중복 검출 |
| **내용 충돌 분석** | Azure OpenAI GPT-4-mini | 유사 문서 쌍 간 의미 비교 → 상충 여부 분석 |
| **문서 주기 관리** | Azure Functions + Table | 오래된 문서 자동 탐지 및 리포트 생성 |
| **민감정보 탐지** | Regex + GPT | 개인정보·보안 키워드 탐지 및 경고 |
| **담당자 관리** | Table Storage `DocspaceOwners` | 문서별 담당자명, 이메일, 연락처 저장 |
| ~~**자동 알림 전송**~~ | Logic Apps / Graph API | 담당자에게 메일/Teams 알림 자동 발송 |
| **종합 보고서 저장** | Blob Reports | 모든 경고/이상 문서 종합 JSON 저장 |

---

## 🧰 기술 스택

| 구분 | 내용 |
|------|------|
| Language | Python 3.12 |
| Framework | Streamlit, Azure Functions |
| AI/ML | Azure OpenAI (GPT-4o-mini, Embeddings) |
| Search | Azure AI Search (Vector Search) |
| Storage | Azure Blob / Table |
| Notification | Microsoft Graph API, Teams Webhook |
| Infra | Azure App Service (Linux, Consumption Plan) |
| Scheduler | Azure Functions Timer Trigger |
| Auth | Storage Key + MS Graph OAuth2 |

---

## 🧩 인덱스 스키마 예시

```json
{
  "name": "docspace-index",
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true},
    {"name": "name", "type": "Edm.String", "searchable": true},
    {"name": "content", "type": "Edm.String", "searchable": true},
    {"name": "contentVector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 1536, "vectorSearchProfile": "vdb-hnsw"},
    {"name": "lastModified", "type": "Edm.String", "sortable": true},
    {"name": "views", "type": "Edm.Int32"},
    {"name": "source", "type": "Edm.String"},
    {"name": "path", "type": "Edm.String"}
  ],
  "vectorSearch": {
    "profiles": [{"name": "vdb-hnsw", "algorithm": "hnsw"}],
    "algorithms": [{"name": "hnsw", "kind": "hnsw"}]
  }
}
```

---

## 📦 코드 구조

```bash
ktds_ms-ai-dev/
├── app.py                  # Streamlit 메인 대시보드
├── files_hub.py            # 파일 허브 (문서 색인/업서트)
├── search.py               # Cognitive Search + Vector Search
├── storage_blob.py         # Blob 업로드/다운로드 유틸
├── storage_table.py        # Table Storage CRUD
├── openai_client.py        # GPT/Embedding 호출
├── functions/
│   └── timer_report.py     # Azure Function (정기 보고서 생성)
├── config.py               # 환경 설정 (Storage Key / Endpoint)
├── requirements.txt
└── README.md               # (현재 파일)
```

---

## 🔄 동작 흐름

1. **문서 업로드** 
→ Blob Storage 저장  
→ 텍스트 추출 (OCR/DocIntel), Embedding 수행, Search 인덱스 업서트 (`upsert_documents_with_embeddings()`)
→ 담당자 지정

3. **유사 문서 탐색** 
→ vector 유사도 검색 및 AI 분석으로 병합 가이드 제시  

4. **문서 감사/보안탐지**
→ PII(주민번호, Mail, 카드번호 등) 탐지  

5. **알림 및 보고**
→ 별도 종합보고서 작성 및 저장

6. **대시보드 모니터링**
→ 활동 로그, 특이사항 표기

---

## 🕒 정기 스케줄 (Azure Functions)

| 항목 | 설정값 |
|------|--------|
| 트리거 | TimerTrigger |
| 주기 | `0 */5 * * * *` (5분마다) |
| 런타임 | Python |
| 인증 | Storage Key |
| 주요 로직 | 오래된 문서 탐색 → Blob에 리포트 저장 → Teams/Mail 전송 |

---

## 💻 실행 및 배포

**App Service Startup Command**
```bash
python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0
```

환경 변수는 App Service 구성에서 설정

**Function App**
- 런타임: Python
- 타이머 트리거: `0 */5 * * * *`
- 인증 방식: Storage Key

---

## 🎬 시연 시나리오

| 단계 | 설명 | 확인 포인트 |
|------|------|-------------|
| ① | Streamlit 접속 | “📁 파일 허브” 탭 표시 |
| ② | 문서 업로드 | 업로드 후 “인덱싱 완료” |
| ③ | 유사 문서 탐색 | Top-k 유사 문서 표시 |
| ④ | 병합 가이드 클릭 | GPT-4 비교결과 표시 |
| ⑤ | 문서 감사 탭 이동 | 오래된 문서 목록 표시 |
| ⑥ | 보고서 저장 | Blob에 `docspace-reports/report.json` 생성 |
| ⑦ | Function 로그 확인 | Timer Trigger 실행 로그 |
| ⑧ | 메일/Teams 확인 | 담당자별 자동 알림 수신 |

---

## 📈 기대 효과

✅ 문서 중복 및 상충 관리 자동화  
✅ 보안/민감 문서 실시간 탐지  
✅ 담당자별 자동 보고 체계 확립  
✅ AI 기반 RAG·문서 질의 확장성 확보  

---



## 장기 비전

“DocSpace AI는 Azure의 AI + Search + Storage + Automation을 통합해  
 문서 관리의 ‘검색 → 분석 → 통보’ 전 주기를 자동화한 차세대 문서 인텔리전스 허브”
 
DocSpace AI는 단순한 검색/리뷰 도구를 넘어 “문서의 품질·보안·가치를 스스로 관리하는 AI 문서 운영 플랫폼”으로 확장
>
M365 (Ondrive, Teams, Outlook 등) 제품들과의 연동
>
RAG + Agent Orchestration → 지식 유지보수 자동화
>
문서 메타데이터 + 조직 데이터 결합 → 부서별 문서 트렌드 분석
>
생성형 AI + 정책엔진(Purview, Entra) → AI Governance 기반 DocOps
