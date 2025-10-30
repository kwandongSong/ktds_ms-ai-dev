링크 : https://kwand-wepapp-1030.azurewebsites.net/
계정 : ktds7_14@modulabsbiz.onmicrosoft.com / modu123!

🧠 DocSpace AI — Azure 기반 문서 인텔리전스 허브

KT DS WorksAI R&D Project
문서 색인, 유사 문서 탐색, 민감정보 탐지 및 자동 보고 기능을 갖춘 AI 문서 관리 플랫폼

<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/c0a21103-512d-4697-a573-24f3155b255f" />

📘 개요

DocSpace AI는 조직 내 문서 자산을 자동으로 색인화하고,
유사도 분석 및 GPT 기반 감사 기능을 통해
문서 관리의 정확도·효율성을 높이는 AI 문서 감사 솔루션입니다.

비정형 문서 → 텍스트 추출 → 임베딩 → 벡터 검색 → 감사/알림
까지 전 과정을 Azure 상에서 자동화

🏗️ 시스템 아키텍처
flowchart LR
    subgraph Client
        A[사용자 / 관리자]
    end
    subgraph App["Azure App Service (Streamlit WebApp)"]
        B1[파일 허브 업로드]
        B2[문서 감사 지원]
        B3[유사 문서 탐색/병합]
    end
    subgraph Search["Azure Cognitive Search"]
        C1[벡터 인덱스 docspace-index]
        C2[contentVector 필드 (1536차원)]
    end
    subgraph AI["Azure OpenAI Service"]
        D1[GPT-4o: 충돌/요약]
        D2[text-embedding-3-small: 임베딩]
    end
    subgraph Storage["Azure Storage"]
        E1[Blob: 원본 문서, 리포트 저장]
        E2[Table: DocspaceOwners, DocspaceActivity]
    end
    subgraph Automation["Azure Functions / Logic Apps"]
        F1[Timer Trigger (5분마다)]
        F2[보고서 생성 및 담당자별 알림]
        F3[Teams / Mail 전송]
    end

    A --> App
    B1 --> E1
    B1 --> C1
    B1 --> D2
    B2 --> D1
    B3 --> C1
    B3 --> D1
    F1 --> E2
    F1 --> E1
    F2 --> F3

☁️ Azure 리소스 구성 요약
영역	리소스명	역할	비고
AI Search	Azure Cognitive Search	문서 인덱싱 + 벡터 검색	contentVector 필드 사용
AI Model	Azure OpenAI	GPT-4o / text-embedding-3-small	의미 비교·요약·임베딩
App Service	Streamlit Web App	사용자 UI + 관리 콘솔	Linux 환경
Storage	Blob Storage	문서 저장, 종합 리포트 저장	docspace, docspace-reports
	Table Storage	담당자 / 로그 관리	DocspaceOwners, DocspaceActivity
Functions	Python Timer Trigger	정기 보고서 생성 (5분마다)	Storage Key 인증
Logic Apps / Graph API	Teams / Outlook 알림	담당자별 자동 발송	Mail.Send 권한 필요
⚙️ 주요 기능
기능	기술 구성	설명
문서 색인 및 검색	Cognitive Search + OpenAI Embeddings	문서 내용 임베딩 후 인덱싱 → 벡터 기반 검색
유사 문서 감지	Vector Search (HNSW)	Top-k 유사 문서 탐색으로 중복 검출
내용 충돌 분석	Azure OpenAI GPT-4	유사 문서 쌍 간 의미 비교 → 상충 여부 분석
문서 주기 관리	Azure Functions + Table	오래된 문서 자동 탐지 및 리포트 생성
민감정보 탐지	Regex + GPT	개인정보·보안 키워드 탐지 및 경고
담당자 관리	Table Storage DocspaceOwners	문서별 담당자명, 이메일, 연락처 저장
자동 알림 전송	Logic Apps / Graph API	담당자에게 메일/Teams 알림 자동 발송
종합 보고서 저장	Blob Reports	모든 경고/이상 문서 종합 JSON 저장
🧰 기술 스택
구분	내용
Language	Python 3.12
Framework	Streamlit, Azure Functions
AI/ML	Azure OpenAI (GPT-4o, Embeddings)
Search	Azure Cognitive Search (Vector Search)
Storage	Azure Blob / Table
Notification	Microsoft Graph API, Teams Webhook
Infra	Azure App Service (Linux, Consumption Plan)
Scheduler	Azure Functions Timer Trigger
Auth	Storage Key + MS Graph OAuth2
🧩 인덱스 스키마 예시
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

📦 코드 구조
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

🔄 동작 흐름
① 문서 업로드

사용자가 파일을 업로드하면 → Blob Storage 저장
→ 텍스트 추출 (OCR/DocIntel)
→ OpenAI Embedding 수행
→ Search 인덱스 업서트 (upsert_documents_with_embeddings())

② 유사 문서 탐색

vector_search(query_text) 실행
→ 벡터 기반 Top-k 유사 문서 검색
→ Streamlit에서 유사도 점수 시각화
→ GPT-4 비교로 “중복/차이” 분석 가이드 표시

③ 문서 감사/보안탐지

정기 Function이 Table 로그 조회
→ 180일 이상 갱신 없는 문서 자동 분류
→ Regex+GPT로 민감정보 포함 여부 감지
→ 결과를 Blob(docspace-reports)에 요약 저장

④ 알림 및 보고

Logic Apps / Graph API가 담당자 목록(DocspaceOwners)을 조회
→ 담당자별 리포트 이메일 / Teams 메시지 전송
→ “오늘의 오래된 문서”, “중복 문서”, “민감 문서” 자동 전달

🕒 정기 스케줄 (Azure Functions)
항목	설정값
트리거	TimerTrigger
주기	0 */5 * * * * (5분마다)
런타임	Python
인증	Storage Key
주요 로직	오래된 문서 탐색 → Blob에 리포트 저장 → Teams/Mail 전송
💻 실행 및 배포
1️⃣ App Service 설정

Startup Command

python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0

2️⃣ 환경 변수

App Service → 구성 → 애플리케이션 설정

Key	Value
SEARCH_ENDPOINT	https://kwand-ai-search-1029.search.windows.net

SEARCH_API_KEY	(Admin Key)
SEARCH_INDEX	docspace-index
AZURE_OPENAI_ENDPOINT	(OpenAI endpoint)
AZURE_OPENAI_API_KEY	(API key)
AZURE_OPENAI_EMBED_DIM	1536
DATA_STORAGE_ACCOUNT	kwandstz1029
DATA_STORAGE_KEY	(Storage key)
REPORTS_CONTAINER	docspace-reports
3️⃣ Function 배포

런타임: Python 3.12

설정:

Timer Trigger (0 */5 * * * *)

인증: Storage Key

function.json 예:

{
  "scriptFile": "__init__.py",
  "bindings": [{
    "name": "mytimer",
    "type": "timerTrigger",
    "direction": "in",
    "schedule": "0 */5 * * * *"
  }]
}

🧪 시연 시나리오
단계	설명	확인 포인트
①	Streamlit 접속	“📁 파일 허브” 탭 표시
②	문서 2개 업로드	업로드 후 “인덱싱 완료”
③	유사 문서 탐색 실행	Top-k 유사 문서 리스트 표시
④	병합 가이드 클릭	GPT-4 비교결과 (중복 여부) 표시
⑤	문서 감사 탭 이동	오래된 문서 목록 자동 표시
⑥	보고서 저장 클릭	Blob에 docspace-reports/report.json 생성
⑦	Function 로그 확인	Timer Trigger 실행 로그
⑧	메일/Teams 확인	담당자별 자동 알림 수신
📈 기대 효과

✅ 중복·유사 문서 자동 탐색으로 관리 효율 향상
✅ 문서 상충/보안 위험 실시간 탐지
✅ 담당자 자동 알림으로 운영 투명성 강화
✅ RAG 기반 문서 질의 응용으로 확장 용이

📎 참고 문서

Azure Cognitive Search Vector Search Overview

Azure OpenAI Embeddings API

Azure Functions Timer Trigger

Microsoft Graph Mail.Send

🖼️ 시각 자료 (발표용 예시)
항목	이미지 예시
시스템 전체 아키텍처	

문서 허브 메인 화면	

유사 문서 탐색 결과	

문서 감사 리포트	

Teams 알림 예시	

(이미지 경로: /docs/img/ 하위에 배치 후 md에 반영 가능)

✅ 발표용 결론 문장

“DocSpace AI는 Azure의 AI + Search + Storage + Automation을 통합해
문서 관리의 ‘검색 → 분석 → 통보’ 전 주기를 자동화한
차세대 문서 인텔리전스 허브입니다.”



### 이슈

- 공유 계정 onedrive 라이센스 오류

* Entra ID '모두의 연구소' 테넌트 - 개인 외부 계정 초대, 사용
* 개인 계정도 라이센스 이슈로 인해 blob storage 지원 가능하도록 기능 수정

- Document Intelligence OCR 오류 (404 - 이전 api endpoint 호출(2024년 기준)/401 (요금제))

* 예전 api 인터페이스로 호출 (AI 모델 학습 시기 기준)
  {endpoint}/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2024-11-30
  ->
  {endpoint}/documentintelligence/documentModels/prebuilt-read:analyze?\_overload=analyzeDocument&api-version=2024-11-30

* Pricing tier 변경 : Free 요금제로 설정 -> Standard 요금제로 설정 후 key 재설정
