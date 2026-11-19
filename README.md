# K-12 수학 RAG 튜터 데이터·인덱스 파이프라인 (`pipelines/`)

이 문서는 `k12-math-rag-tutor/pipelines` 폴더의 단계별 파일 구성, 주요 함수 및 입출력 경로, 실행 순서를 정리한 안내 문서입니다.

## 단계별 파일 안내

| 순서 | 파일명 | 주요 역할 |
| :--- | :--- | :--- |
| 사전 준비 | `.env` | API 키 및 실행 환경 변수 설정 |
| 사전 준비 | `AIHubData_unzipped.ipynb` | AI-Hub 수학 교과 문제 풀이과정 데이터 압축 해제 및 초기 탐색 |
| 사전 준비 | `run_pipeline.ipynb` | 코랩/로컬 환경에서 파이프라인 단계별 실행 및 점검 |
| 1단계 | `01_fetch_sources.py` | 원본 문제/교과/참고 자료 수집 및 경로 초기화 |
| 2단계 | `02_parse_answers_and_q.py` | 문항 본문과 정답·풀이 단계 분리 및 파싱 |
| 3단계 | `03_vlm_math_figure.py` / `03_vlm_math_figure_auto.py` | 기하·그래프·도형 이미지의 VLM 기반 텍스트/수식 설명 추출 |
| 4단계 | `04_normalize_aihub.py` | AI-Hub 데이터 포맷 통일 및 정제 |
| 4단계 | `04_tag_curriculum_meta.py` | 단원 분류, 선수학습(`prerequisites`), 다음 단원(`next_units`), 핵심 키워드(`keywords`) 부여 |
| 5단계 | `05_build_faiss_index.py` | 정제·태깅된 문항/풀이 청크를 임베딩하여 FAISS 인덱스(`dirs["indexes"]`) 구축 |

## 핵심 파일별 상세 명세

| 단계 | 파일명 | 주요 함수 / 상수 | 입력 경로 / 데이터 | 출력 경로 / 산출물 |
| :--- | :--- | :--- | :--- | :--- |
| 3단계 | `03_vlm_math_figure_auto.py` | `resolve_project_root()`, `load_env_files()`, `discover_exam_ids()`, `inspect_merged_status()`, `build_base_runner_command()`, `run_single_exam_isolated()`, `parse_args()`, `main()` | `<project_root>/data/raw/ebsi/h1/{exam_id}_problem.pdf`, `_solution.pdf`, `_answer.pdf` (`GEMINI_API_KEY` 필요, 기본 모델 `gemini-3.8-flash`) | `/content/drive/MyDrive/k12_math_rag_data/structured_exams/{exam_id}/{exam_id}_merged.json`, `batch_auto_report.json` |
| 4단계-A | `04_normalize_aihub.py` | `clean_text()`, `split_problem_vlm_pages()`, `split_solution_vlm_pages()`, `parse_solution_parsed_test()`, `discover_exam_inputs()`, `normalize_exam_records()`, `normalize_aihub_dataset()`, `main()` | `--drive-root`(기본 `/content/drive/MyDrive/k12_math_rag_data`), `structured_exams`, `data` 내 `*_problem_vlm.json`, `*_solution_vlm.json`, `*paserd*/*parsed*.json`, `*_merged.json` | `--output-dir`(기본 `<drive_root>/normalized_exams/<exam_id>/`)에 `{exam_id}_normalized.json`, `{exam_id}_normalized.jsonl` |
| 4단계-B | `04_tag_curriculum_meta.py` | `CURRICULUM_GRAPH`, `classify_question_unit()`, `enrich_normalized_exam()` | `--base-dir/<exam_id>/{exam_id}_normalized.json` (기본 `/content/drive/MyDrive/k12_math_rag_data/normalized_exams/<exam_id>/`) | `{exam_id}_normalized_tagged.json`, `{exam_id}_normalized_tagged.jsonl` (`item["curriculum_meta"]` 추가) |
| 5단계 | `05_build_faiss_index.py` | `build_faiss_index(docs, index_dir, embedding_model_name="BAAI/bge-m3")` | 정규화·메타 태깅된 문항/풀이 문서(`docs`) 및 `get_storage_dirs(root)["indexes"]` | `dirs["indexes"]` 경로의 FAISS 벡터 인덱스 |


## 실행 순서 요약

1. **환경 및 원천 데이터 준비:** `.env` 설정 및 `AIHubData_unzipped.ipynb`로 원본 데이터를 준비합니다.
2. **수집 및 파싱:** `01_fetch_sources.py` → `02_parse_answers_and_q.py` 순으로 실행해 문항과 풀이를 구조화합니다.
3. **도형 VLM 처리:** 도형 포함 문항에 대해 `03_vlm_math_figure.py` 또는 `03_vlm_math_figure_auto.py`를 실행해 시각 정보를 보완합니다.
4. **정규화 및 메타데이터 태깅:** `04_normalize_aihub.py`로 스키마를 맞춘 뒤, `04_tag_curriculum_meta.py`로 단원·선수학습 그래프 정보를 태깅합니다.
5. **벡터 인덱스 생성:** `05_build_faiss_index.py`를 실행해 검색용 FAISS 인덱스를 생성하고 RAG 튜터와 연결합니다.

# K-12 수학 RAG 튜터 파이프라인 실행 및 고도화 계획 (`plan.md`)

## 1. 목표
`k12-math-rag-tutor`의 `pipelines/` 단계별 스크립트(`01_fetch_sources.py`, `02_parse_answers_and_q.py`, `03_vlm_math_figure.py`, `03_vlm_math_figure_auto.py`, `04_normalize_aihub.py`, `04_tag_curriculum_meta.py`, `05_build_faiss_index.py`)와 `AIHubData_unzipped.ipynb`, `run_pipeline.ipynb`를 안정적으로 연계하여, 고등학교 수학 문항·풀이·도형 해석 데이터와 단원 선수학습 메타데이터를 구축하고 FAISS 기반 RAG 튜터 검색 인덱스를 완성합니다.

## 2. 작업 단계별 실행 계획

### Phase 1. 환경 점검 및 원천 데이터 확보
- [ ] `.env` 및 `/content/drive/MyDrive/k12_math_rag_data/.env` 환경변수(`GEMINI_API_KEY` 등) 설정 확인
- [ ] `src/colab_env.py`의 `get_project_root()`, `get_storage_dirs()` 경로 및 저장소 초기화 확인
- [ ] `AIHubData_unzipped.ipynb`로 AI-Hub 수학 데이터 압축 해제 및 초기 데이터 무결성 점검
- [ ] `01_fetch_sources.py` 실행 및 원천 데이터/교과/참고 자료 출력 경로 검증

### Phase 2. 문항·풀이 파싱 및 VLM 도형 해석
- [ ] `02_parse_answers_and_q.py` 실행하여 문제(Q), 정답, 풀이 과정 필드 분리 검증
- [ ] `<project_root>/data/raw/ebsi/h1/` 내 `*_problem.pdf` 및 `*_solution.pdf` 쌍 확인 및 `03_vlm_math_figure_auto.py`를 `--limit 1` 또는 `--exam-ids`로 단일 세트 시험 실행
- [ ] `03_vlm_math_figure.py` 및 `03_vlm_math_figure_auto.py` 실행 결과 비교(누락 도형 여부, 수식/도형 묘사 정확도 확인)
- [ ] `structured_exams/{exam_id}/{exam_id}_merged.json` 및 `batch_auto_report.json`의 `status`(`ok` / `partial` / `quota_exceeded` / `error`)와 누락 문항 번호(`missing_solution_nos`) 점검
- [ ] 쿼터 소진 또는 미완료 문항 발생 시 `--retry-incomplete` 옵션으로 재실행 절차 검증

### Phase 3. 스키마 정규화 및 교육과정 메타데이터 태깅
- [ ] `discover_exam_inputs()`가 대상 `exam_id`의 `*_problem_vlm.json`, `*_solution_vlm.json`, `*paserd*/*parsed*.json`, `*_merged.json` 파일을 누락 없이 수집하는지 확인
- [ ] `split_problem_vlm_pages()`, `split_solution_vlm_pages()`, `parse_solution_parsed_test()`의 문항 번호 분리 및 `figure_description` / `choices` / `intent` / `solution` 추출 품질 검증
- [ ] `04_normalize_aihub.py` 실행 후 `normalized_exams/{exam_id}/{exam_id}_normalized.json` 및 `.jsonl` 생성 확인(`problem_count`, `solution_count`, `answer_count` 및 결측치/LaTeX 점검)
- [ ] 현재 스텁 상태인 `normalize_aihub_dataset()`에 실제 AI-Hub 수학 풀이과정 데이터셋 정규화 로직 구현
- [ ] `04_tag_curriculum_meta.py`의 `enrich_normalized_exam()` 실행 후 `{exam_id}_normalized_tagged.json` / `.jsonl` 생성 및 `curriculum_meta` 매핑 정확도 검증
- [ ] `CURRICULUM_GRAPH`(42개 단원) 및 `intent` 가중치 3 / 본문·해설 가중치 1 기준 분류 결과와 `prerequisite_units`·`next_units` 단원 연결 누락 여부 점검

### Phase 4. FAISS 벡터 인덱스 구축 및 RAG 서비스 연계
- [ ] `{exam_id}_normalized_tagged.jsonl` (또는 `.json`)에서 문항·풀이·도형 묘사·`curriculum_meta`를 결합한 문서(`docs`) 구성 로직 구현
- [ ] `05_build_faiss_index.py`의 `build_faiss_index()` 구현 및 임베딩 모델(`BAAI/bge-m3` 등) 설정 확정
- [ ] `dirs["indexes"]` 경로에 FAISS 인덱스 저장 및 로드 테스트 수행
- [ ] 학생 취약 단원 및 `prerequisite_units` 기반 선수단원 역추적·20분 드릴·단원 필터링(`area`, `prerequisites`, `keywords`)과 벡터 유사도 검색 결합 테스트

### Phase 5. 파이프라인 자동화 및 운영 정리
- [ ] `run_pipeline.ipynb`에서 01 → 02 → 03 → 04 → 05 단계 순차 실행 및 중간 산출물 체크포인트 구성
- [ ] 불필요한 임시/중복 파일(`03_vlm_math_figure.cpython-312.pyc`, 미사용 스크립트 등) 정리 및 `.gitignore` 점검
- [ ] `README.md` / `pipeline.md`와 실제 구현 코드 간 입출력 경로, 함수명, 인자 동기화

## 3. 확인된 주의사항 및 리스크
- **인코딩 및 경로 이슈:** Windows 환경에서 `.py`, `.json`, `.jsonl`, `.md` 파일 입출력 시 UTF-8 인코딩을 명시해 한글 깨짐을 방지하고, 코랩 임시 경로(`/content/...`)와 구글 드라이브 경로(`/content/drive/MyDrive/...`)를 구분해 관리해야 합니다.
- **모델명 및 격리 실행 경로 점검:** `03_vlm_math_figure_auto.py`는 기본 모델명이 `gemini-3.8-flash`로 설정되어 있고, 격리 실행 시 `data/raw/ebsi/h1` 및 `/content/k12_auto_stage_raw/ebsi/h1` 경로를 사용하므로 실제 실행 환경과 모델명·디렉터리 일치 여부를 확인해야 합니다.
- **VLM 쿼터·재시도 및 파일명 패턴 주의:** 일시적 `429` 오류는 지수 백오프로 재시도하고 일일 한도 초과 시 즉시 중단되며, `04_normalize_aihub.py`에는 `paserd` 오탈자 파일명 패턴(`solution_paserd_test.json`) 탐색 조건이 포함되어 있으므로 실제 파일명과 대조해야 합니다.
- **인덱스 재생성 기준:** `04_normalize_aihub.py`나 `04_tag_curriculum_meta.py` 수정 시 `05_build_faiss_index.py`를 재실행하여 인덱스와 메타데이터 버전을 일치시킵니다.

---
# K-12 수학 RAG 튜터 데이터·인덱스 파이프라인 (`pipelines/`)

이 문서는 `k12-math-rag-tutor/pipelines` 폴더의 실제 구현 로직을 바탕으로 한 실행 절차, 입출력 경로, 단원 메타데이터 흐름, 그리고 Mermaid 순서도를 정리한 문서입니다.

## 전체 파이프라인 실행 흐름도

```mermaid
flowchart TD
    subgraph ENV["0. 환경변수 및 저장소 경로 초기화"]
        ENV_FILE[".env 및<br/>/content/drive/MyDrive/k12_math_rag_data/.env"]
        COLAB_ENV["src/colab_env.py<br/>(get_project_root / get_storage_dirs)"]
        RAW_PDF["원본 시험지 PDF<br/>data/raw/ebsi/h1/{exam_id}_problem.pdf<br/>{exam_id}_solution.pdf (_answer.pdf)"]
    end

    subgraph STAGE_03["3단계: EBSi 시험지 VLM 일괄 파싱 및 상태 점검"]
        P03_AUTO["03_vlm_math_figure_auto.py<br/>discover_exam_ids() · inspect_merged_status()<br/>run_single_exam_isolated() · main()"]
        ISOLATED["임시 격리 폴더 & 서브프로세스<br/>/content/k12_auto_stage_raw/ebsi/h1<br/>pipelines.03_vlm_math_figure 실행<br/>(429 지수 백오프 · 일일 쿼터 초과 즉시 중단)"]
        MERGED_JSON[("structured_exams/{exam_id}/{exam_id}_merged.json")]
        REPORT_JSON[("batch_auto_report.json<br/>(ok / partial / quota_exceeded / error)")]
    end

    subgraph STAGE_04_NORM["4단계-A: 문항·해설·도형 스키마 정규화"]
        P04_NORM["04_normalize_aihub.py<br/>discover_exam_inputs() · split_problem_vlm_pages()<br/>split_solution_vlm_pages() · parse_solution_parsed_test()<br/>normalize_exam_records() · main()"]
        VLM_INPUTS["입력 JSON 탐색<br/>*_problem_vlm.json · *_solution_vlm.json<br/>*paserd*/*parsed*.json · *_merged.json"]
        NORM_OUT[("normalized_exams/{exam_id}/<br/>{exam_id}_normalized.json<br/>{exam_id}_normalized.jsonl")]
    end

    subgraph STAGE_04_TAG["4단계-B: 교육과정 진도표 기반 메타데이터 태깅"]
        P04_TAG["04_tag_curriculum_meta.py<br/>CURRICULUM_GRAPH (42개 단원)<br/>classify_question_unit() · enrich_normalized_exam()"]
        TAG_OUT[("normalized_exams/{exam_id}/<br/>{exam_id}_normalized_tagged.json<br/>{exam_id}_normalized_tagged.jsonl<br/>(item.curriculum_meta)")]
    end

    subgraph STAGE_05["5단계: FAISS 벡터 인덱스 구축 및 RAG 연계"]
        P05["05_build_faiss_index.py<br/>build_faiss_index(docs, index_dir, embedding_model_name='BAAI/bge-m3')"]
        IDX_STORE[("dirs['indexes']<br/>FAISS 인덱스 저장소")]
        RAG_APP["RAG 튜터 앱<br/>(최소성취수준 보정·20분 드릴·선수단원 역추적)"]
    end

    ENV_FILE --> P03_AUTO
    COLAB_ENV -. "저장 경로 제공" .- P04_NORM
    COLAB_ENV -. "저장 경로 제공" .- P05
    RAW_PDF --> P03_AUTO
    P03_AUTO --> ISOLATED
    ISOLATED --> MERGED_JSON
    P03_AUTO --> REPORT_JSON

    MERGED_JSON --> VLM_INPUTS
    VLM_INPUTS --> P04_NORM
    P04_NORM --> NORM_OUT

    NORM_OUT --> P04_TAG
    P04_TAG --> TAG_OUT

    TAG_OUT --> P05
    P05 --> IDX_STORE
    IDX_STORE --> RAG_APP