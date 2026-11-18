from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# 수학진도표.png 기반 단원 마스터 (영역, 선수 단원, 후속 단원, 매칭 키워드)
CURRICULUM_GRAPH: dict[str, dict[str, Any]] = {
    "다항식의 연산": {
        "area": "공통수학(다항식)",
        "prerequisites": [],
        "next_units": ["나머지정리"],
        "keywords": ["다항식", "A+B", "A-B", "전개", "곱셈 공식", "다항식 계산"],
    },
    "나머지정리": {
        "area": "공통수학(다항식)",
        "prerequisites": ["다항식의 연산"],
        "next_units": ["인수분해"],
        "keywords": ["나머지정리", "나누었을 때의 나머지", "나누어떨어지고", "인수정리", "몫은"],
    },
    "인수분해": {
        "area": "공통수학(다항식)",
        "prerequisites": ["나머지정리"],
        "next_units": ["복소수", "여러 가지 방정식"],
        "keywords": ["인수분해"],
    },
    "복소수": {
        "area": "공통수학(방정식과 부등식)",
        "prerequisites": ["인수분해"],
        "next_units": ["이차방정식"],
        "keywords": ["복소수", "켤레복소수", "허수", "실수부분", "허수부분"],
    },
    "이차방정식": {
        "area": "공통수학(방정식과 부등식)",
        "prerequisites": ["복소수"],
        "next_units": ["이차방정식과 이차함수"],
        "keywords": ["이차방정식", "판별식", "근과 계수의 관계", "실근", "허근"],
    },
    "이차방정식과 이차함수": {
        "area": "공통수학(방정식과 부등식)",
        "prerequisites": ["이차방정식"],
        "next_units": ["여러 가지 방정식", "도함수의 활용"],
        "keywords": ["이차함수", "최댓값", "최솟값", "꼭짓점", "이차함수의 최대와 최소"],
    },
    "여러 가지 방정식": {
        "area": "공통수학(방정식과 부등식)",
        "prerequisites": ["인수분해", "이차방정식과 이차함수"],
        "next_units": ["여러 가지 부등식"],
        "keywords": ["삼차방정식", "사차방정식", "연립방정식", "연립이차방정식"],
    },
    "여러 가지 부등식": {
        "area": "공통수학(방정식과 부등식)",
        "prerequisites": ["여러 가지 방정식"],
        "next_units": ["함수"],
        "keywords": ["부등식", "절댓값을 포함한", "일차부등식", "이차부등식", "연립부등식"],
    },
    "집합": {
        "area": "공통수학(집합과 명제)",
        "prerequisites": [],
        "next_units": ["명제"],
        "keywords": ["집합", "부분집합", "교집합", "합집합", "여집합", "차집합"],
    },
    "명제": {
        "area": "공통수학(집합과 명제)",
        "prerequisites": ["집합"],
        "next_units": ["명제의 증명"],
        "keywords": ["명제", "조건", "진리집합", "역", "대우", "충분조건", "필요조건"],
    },
    "명제의 증명": {
        "area": "공통수학(집합과 명제)",
        "prerequisites": ["명제"],
        "next_units": ["함수", "수학적 귀납법"],
        "keywords": ["명제의 증명", "귀류법", "산술평균", "기하평균", "코시-슈바르츠"],
    },
    "함수": {
        "area": "공통수학(함수)",
        "prerequisites": ["여러 가지 부등식", "명제의 증명", "도형의 이동"],
        "next_units": ["지수함수와 로그함수", "함수의 극한"],
        "keywords": ["합성함수", "역함수", "일대일대응", "함수의 뜻"],
    },
    "유리함수와 무리함수": {
        "area": "공통수학(함수)",
        "prerequisites": ["함수"],
        "next_units": ["함수의 극한"],
        "keywords": ["유리함수", "무리함수", "점근선", "유리식", "무리식"],
    },
    "행렬과 그 연산": {
        "area": "공통수학(행렬)",
        "prerequisites": [],
        "next_units": [],
        "keywords": ["행렬", "이차정사각행렬", "성분", "행렬의 실수배", "행렬의 연산"],
    },
    "평면좌표": {
        "area": "공통수학(도형의 방정식)",
        "prerequisites": [],
        "next_units": ["직선의 방정식"],
        "keywords": ["두 점 사이의 거리", "내분점", "외분점", "평면좌표", "무게중심"],
    },
    "직선의 방정식": {
        "area": "공통수학(도형의 방정식)",
        "prerequisites": ["평면좌표"],
        "next_units": ["원의 방정식", "도함수의 활용"],
        "keywords": ["직선의 방정식", "평행 조건", "수직", "점과 직선 사이의 거리", "기울기"],
    },
    "원의 방정식": {
        "area": "공통수학(도형의 방정식)",
        "prerequisites": ["직선의 방정식"],
        "next_units": ["도형의 이동"],
        "keywords": ["원의 방정식", "접선", "중심", "반지름", "현의 길이"],
    },
    "도형의 이동": {
        "area": "공통수학(도형의 방정식)",
        "prerequisites": ["원의 방정식"],
        "next_units": ["함수"],
        "keywords": ["평행이동", "대칭이동", "도형의 이동"],
    },
    "합의 법칙과 곱의 법칙": {
        "area": "공통수학(경우의 수)",
        "prerequisites": [],
        "next_units": ["순열과 조합"],
        "keywords": ["합의 법칙", "곱의 법칙", "경우의 수", "주사위", "순서쌍"],
    },
    "순열과 조합": {
        "area": "공통수학(경우의 수)",
        "prerequisites": ["합의 법칙과 곱의 법칙"],
        "next_units": ["이항정리", "확률의 뜻과 활용"],
        "keywords": ["순열", "조합", "\\mathrm{P}", "\\mathrm{C}"],
    },
    # 대수 / 수학I
    "지수와 로그": {"area": "대수", "prerequisites": [], "next_units": ["지수함수와 로그함수"], "keywords": ["거듭제곱근", "지수", "로그", "상용로그"]},
    "지수함수와 로그함수": {"area": "대수", "prerequisites": ["지수와 로그", "함수"], "next_units": [], "keywords": ["지수함수", "로그함수"]},
    "삼각함수": {"area": "대수", "prerequisites": [], "next_units": ["삼각함수의 그래프", "사인법칙과 코사인법칙"], "keywords": ["호도법", "부채꼴", "삼각함수"]},
    "삼각함수의 그래프": {"area": "대수", "prerequisites": ["삼각함수"], "next_units": [], "keywords": ["삼각함수의 그래프", "주기", "삼각방정식", "삼각부등식"]},
    "사인법칙과 코사인법칙": {"area": "대수", "prerequisites": ["삼각함수"], "next_units": [], "keywords": ["사인법칙", "코사인법칙", "삼각형의 넓이"]},
    "등차수열과 등비수열": {"area": "대수", "prerequisites": [], "next_units": ["수열의 합"], "keywords": ["등차수열", "등비수열", "공차", "공비"]},
    "수열의 합": {"area": "대수", "prerequisites": ["등차수열과 등비수열"], "next_units": ["수학적 귀납법"], "keywords": ["수열의 합", "\\sum", "시그마"]},
    "수학적 귀납법": {"area": "대수", "prerequisites": ["수열의 합", "명제의 증명"], "next_units": [], "keywords": ["수학적 귀납법", "귀납적 정의"]},
    # 미적분I / 수학II
    "함수의 극한": {"area": "미적분Ⅰ", "prerequisites": ["함수", "유리함수와 무리함수"], "next_units": ["함수의 연속"], "keywords": ["함수의 극한", "\\lim"]},
    "함수의 연속": {"area": "미적분Ⅰ", "prerequisites": ["함수의 극한"], "next_units": ["미분계수"], "keywords": ["함수의 연속", "불연속", "사잇값 정리"]},
    "미분계수": {"area": "미적분Ⅰ", "prerequisites": ["함수의 연속"], "next_units": ["도함수"], "keywords": ["미분계수", "평균변화율", "미분가능"]},
    "도함수": {"area": "미적분Ⅰ", "prerequisites": ["미분계수"], "next_units": ["도함수의 활용", "부정적분"], "keywords": ["도함수", "미분법"]},
    "도함수의 활용": {"area": "미적분Ⅰ", "prerequisites": ["도함수", "이차방정식과 이차함수", "직선의 방정식"], "next_units": ["정적분", "정적분의 활용"], "keywords": ["도함수의 활용", "극대", "극소", "접선의 방정식", "평균값 정리"]},
    "부정적분": {"area": "미적분Ⅰ", "prerequisites": ["도함수"], "next_units": ["정적분"], "keywords": ["부정적분"]},
    "정적분": {"area": "미적분Ⅰ", "prerequisites": ["부정적분", "도함수의 활용"], "next_units": ["정적분의 활용"], "keywords": ["정적분", "\\int"]},
    "정적분의 활용": {"area": "미적분Ⅰ", "prerequisites": ["정적분", "도함수의 활용"], "next_units": [], "keywords": ["정적분의 활용", "넓이", "속도와 거리"]},
    # 확률과 통계
    "이항정리": {"area": "확률과 통계", "prerequisites": ["순열과 조합"], "next_units": ["이산확률변수와 확률분포"], "keywords": ["이항정리", "이항계수"]},
    "확률의 뜻과 활용": {"area": "확률과 통계", "prerequisites": ["순열과 조합"], "next_units": ["조건부확률", "이산확률변수와 확률분포"], "keywords": ["확률의 뜻", "여사건", "덧셈정리"]},
    "조건부확률": {"area": "확률과 통계", "prerequisites": ["확률의 뜻과 활용"], "next_units": ["이산확률변수와 확률분포"], "keywords": ["조건부확률", "독립사건", "독립시행"]},
    "이산확률변수와 확률분포": {"area": "확률과 통계", "prerequisites": ["이항정리", "확률의 뜻과 활용", "조건부확률"], "next_units": ["연속확률변수와 확률분포"], "keywords": ["이산확률변수", "기댓값", "이항분포"]},
    "연속확률변수와 확률분포": {"area": "확률과 통계", "prerequisites": ["이산확률변수와 확률분포"], "next_units": ["통계적 추정"], "keywords": ["연속확률변수", "정규분포", "표준정규분포"]},
    "통계적 추정": {"area": "확률과 통계", "prerequisites": ["연속확률변수와 확률분포"], "next_units": [], "keywords": ["통계적 추정", "표본평균", "신뢰구간"]},
}


def classify_question_unit(item: dict[str, Any]) -> dict[str, Any]:
    intent = item.get("intent") or ""
    q_text = item.get("question_text") or ""
    sol_text = item.get("solution") or ""

    # 출제의도(intent)에 가중치 3배, 문제/해설 본문에 가중치 1배 부여
    best_unit = "미분류"
    best_score = 0
    matched_keywords: list[str] = []

    for unit_name, meta in CURRICULUM_GRAPH.items():
        score = 0
        hits: list[str] = []
        for kw in meta["keywords"]:
            if kw in intent:
                score += 3
                hits.append(kw)
            elif kw in q_text or kw in sol_text:
                score += 1
                hits.append(kw)
        if score > best_score:
            best_score = score
            best_unit = unit_name
            matched_keywords = list(dict.fromkeys(hits))

    if best_unit in CURRICULUM_GRAPH:
        info = CURRICULUM_GRAPH[best_unit]
        return {
            "unit_name": best_unit,
            "subject_area": info["area"],
            "prerequisite_units": info["prerequisites"],
            "next_units": info["next_units"],
            "matched_keywords": matched_keywords,
            "curriculum_tags": [info["area"], best_unit, *info["prerequisites"]],
        }

    return {
        "unit_name": "미분류",
        "subject_area": "미분류",
        "prerequisite_units": [],
        "next_units": [],
        "matched_keywords": [],
        "curriculum_tags": [],
    }


def enrich_normalized_exam(exam_dir: Path, exam_id: str) -> None:
    json_path = exam_dir / f"{exam_id}_normalized.json"
    jsonl_path = exam_dir / f"{exam_id}_normalized.jsonl"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    for item in data.get("items", []):
        item["curriculum_meta"] = classify_question_unit(item)

    tagged_json_path = exam_dir / f"{exam_id}_normalized_tagged.json"
    tagged_jsonl_path = exam_dir / f"{exam_id}_normalized_tagged.jsonl"

    tagged_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with tagged_jsonl_path.open("w", encoding="utf-8") as f:
        for item in data.get("items", []):
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[메타 태깅 완료] {tagged_json_path}")
    print(f"[메타 태깅 완료] {tagged_jsonl_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="수학 진도표 기반 정규화 문항 메타 태깅")
    parser.add_argument("--exam-id", type=str, default="2026_10_hs1")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("/content/drive/MyDrive/k12_math_rag_data/normalized_exams"),
    )
    args = parser.parse_args()
    enrich_normalized_exam(args.base_dir / args.exam_id, args.exam_id)