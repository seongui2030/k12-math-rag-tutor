k12-math-rag-tutor/
├── README.md
├── pyproject.toml / requirements.txt
├── .env.example              # 실제 키는 제외하고 변수명만 예시로 관리
├── sitecustomize.py          # 런타임 전역 훅(선택/최소 유지)
├── src/                      # [핵심 도메인 로직] 재사용 가능한 순수 모듈/클래스
│   ├── __init__.py
│   ├── config.py             # 환경변수 로드, 경로/모델명 상수 중앙 관리
│   ├── vlm/                  # VLM 호출·페일오버·프롬프트 응집 폴더
│   │   ├── __init__.py
│   │   ├── failover.py       # VLMFailoverRunner, Gemini/Claude 호출, 훅
│   │   └── prompts.py        # 문제/해설/수식 추출 프롬프트 모음
│   ├── pdf_parser/           # PDF 렌더링, 페이지 분할, 병합 로직
│   │   ├── __init__.py
│   │   └── exam_merger.py
│   └── rag/                  # RAG 인덱싱, 검색, 튜터 응답 로직
│       ├── __init__.py
│       └── retriever.py
├── pipelines/                # [실행 오케스트레이션] CLI/배치 실행 단위 스크립트
│   ├── __init__.py
│   └── 03_vlm_math_figure_auto.py
├── scripts/                  # [단발성·로컬 유틸리티] 로컬 테스트, 점검, 마이그레이션
│   └── run_local_qwen_vl.py
├── notebooks/                # [탐색/실험용] Colab 노트북 (.ipynb) 모음
│   └── run_pipeline.ipynb
└── tests/                    # [검증] 임포트/문법/페일오버 단위 테스트
    └── test_vlm_failover.py