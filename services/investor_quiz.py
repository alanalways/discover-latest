"""Investor personality quiz scoring."""

from __future__ import annotations

from typing import Dict, List

PERSONALITY_TYPES = {
    "guardian": {"name": "穩健守護者", "style": "偏好穩定現金流與防禦型資產"},
    "hunter": {"name": "成長獵手", "style": "偏好高成長與產業趨勢機會"},
    "surfer": {"name": "趨勢衝浪者", "style": "偏好順勢交易與動能策略"},
    "explorer": {"name": "價值探索家", "style": "偏好低估值與安全邊際"},
}

OCCUPATION_WEIGHT = {
    "student": {"guardian": 2, "risk_cap": 50},
    "retired": {"guardian": 4, "risk_cap": 40},
    "salaried": {"guardian": 1, "risk_cap": 80},
    "freelance": {"surfer": 2, "risk_cap": 75},
    "business_owner": {"hunter": 2, "risk_cap": 90},
    "finance_pro": {"hunter": 1, "explorer": 1, "risk_cap": 100},
    "other": {"risk_cap": 70},
}

INCOME_RISK_BONUS = {
    "lt_50k": -8,
    "50k_100k": -2,
    "100k_300k": 4,
    "300k_1m": 8,
    "gt_1m": 12,
}

# 10-question lightweight scoring; answer value expected in [1..5].
QUESTION_WEIGHTS = [
    {"guardian": 1.4, "explorer": 0.6},
    {"hunter": 1.3, "surfer": 0.7},
    {"surfer": 1.2, "hunter": 0.8},
    {"explorer": 1.3, "guardian": 0.7},
    {"guardian": 1.0, "explorer": 1.0},
    {"hunter": 1.2, "surfer": 0.8},
    {"surfer": 1.4, "hunter": 0.6},
    {"explorer": 1.2, "guardian": 0.8},
    {"guardian": 1.1, "explorer": 0.9},
    {"hunter": 1.0, "surfer": 1.0},
]


def _norm_answer(value: int) -> int:
    try:
        iv = int(value)
    except Exception:
        return 3
    return max(1, min(5, iv))


def calculate_profile(answers: List[int], occupation: str = "other", income: str = "50k_100k") -> Dict:
    scores = {"guardian": 0.0, "hunter": 0.0, "surfer": 0.0, "explorer": 0.0}
    norm_answers = [_norm_answer(v) for v in (answers or [])][:10]
    while len(norm_answers) < 10:
        norm_answers.append(3)

    for idx, answer in enumerate(norm_answers):
        scaled = (answer - 3) / 2.0  # [-1, 1]
        for ptype, weight in QUESTION_WEIGHTS[idx].items():
            scores[ptype] += scaled * weight

    occ_key = occupation if occupation in OCCUPATION_WEIGHT else "other"
    occ_w = OCCUPATION_WEIGHT[occ_key]
    for key in ("guardian", "hunter", "surfer", "explorer"):
        if key in occ_w:
            scores[key] += float(occ_w[key])

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = ordered[0][0]
    secondary = ordered[1][0]

    base_risk = 50 + (scores["hunter"] + scores["surfer"] - scores["guardian"] - scores["explorer"]) * 8
    risk_cap = int(occ_w.get("risk_cap", 70))
    income_bonus = int(INCOME_RISK_BONUS.get(income, 0))
    risk_score = int(max(10, min(risk_cap, round(base_risk + income_bonus))))

    return {
        "primary": primary,
        "secondary": secondary,
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "risk_score": risk_score,
        "occupation": occupation,
        "income": income,
        "profile_name": PERSONALITY_TYPES[primary]["name"],
        "profile_style": PERSONALITY_TYPES[primary]["style"],
    }
