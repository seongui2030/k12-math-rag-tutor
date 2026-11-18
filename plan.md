
# 중장기 개발 및 고도화 단계 (Step-by-Step Roadmap)

## Phase 1: 데이터베이스 연동 및 멀티 스키마 구축 (Supabase / SQLite)

* [ ] 학생 정보 테이블 (`id`, `password`, `name`, `role`, `level`, `class_info`) 설계[cite: 4]
* [ ] 문제 뱅크 테이블 (`level`, `question`, `answer`, `explanation`, `ai_hub_meta`) 구축[cite: 4]
* [ ] 학습 이력 및 일별 풀이 결과 로그 테이블 구축[cite: 4]

## Phase 2: 권한별 UI/UX 구현 (Gradio Multi-View)

* [ ] 인트로 및 로그인 화면:
  * 법적 필수 출처 표기 문구 삽입[cite: 4]
  * 권한(학생/교사/관리자)별 분기 처리[cite: 4]
* [ ] 학생 화면:
  * 최초 로그인 시 비밀번호 변경 모달/폼[cite: 4]
  * 단원별 모의고사 진단 평가 UI[cite: 4]
  * 매일 아침 3문항 푸시 및 제출 결과 피드백 UI[cite: 4]
* [ ] 교사 화면:
  * 담당 학급 학생 리스트 및 진도/참여 현황 대시보드[cite: 4]
* [ ] 관리자 화면:
  * 1학년 신입생 일괄 ID 생성 (CSV 일괄 업로드 또는 자동 생성)[cite: 4]
  * 패스워드 초기화 기능[cite: 4]
  * 예외 휴일(학교 행사의 날) 캘린더 등록 기능[cite: 4]

## Phase 3: AI-Hub 데이터 연동 및 문제 확장

* [ ] AI-Hub 수학 교과 문제 풀이과정 데이터 메타데이터 파싱 스크립트 작성[cite: 4]
* [ ] 난이도별(상·중·하) 문항 풀 자동 적재 프로세스 구축[cite: 4]

## Phase 4: 배포 및 운영 안정화

* [ ] Hugging Face Spaces (`lilyjeongwon/qwen-vl`) 환경 설정 (`app.py`, `README.md` YAML Frontmatter 최적화)[cite: 4]
* [ ] 365일 무중단 루틴 운영 테스트 및 예외 처리 검증[cite: 4]
