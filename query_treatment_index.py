"""Query the compiled kidney treatment index.

This is a small read-only helper for fourth-stage query regression. It does not
rebuild clinical data; it only reads files under compiled/.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
DEFAULT_COMPILED_DIR = APP_DIR / "compiled"
DISPLAY_ZH_FILENAME = "display_zh.json"
EVIDENCE_DIGEST_ZH_FILENAME = "evidence_digest_zh.json"

SECTION_ORDER = {
    "supportive_foundation": 0,
    "classic_regimens": 1,
    "new_targeted_regimens": 2,
    "special_scenarios": 3,
    "exploratory_regimens": 4,
    "not_recommended": 5,
}

SECTION_LABELS_CN = {
    "supportive_foundation": "基础/支持治疗",
    "classic_regimens": "经典方案",
    "new_targeted_regimens": "新药/生物制剂/靶向治疗",
    "special_scenarios": "特殊场景",
    "exploratory_regimens": "探索性/待更新方案",
    "not_recommended": "不推荐",
}

DISPLAY_ENUM_LABELS = {
    "adds_combination_strategy": "增加联合治疗策略信号",
    "adds_conditional_option": "增加条件性治疗选择",
    "adds_exploratory_watchlist": "加入探索性观察清单",
    "adds_selected_branch": "增加选择性治疗分支",
    "adds_special_branch": "增加特殊场景分支",
    "argues_against_routine_use": "反对常规使用",
    "changes_regimen": "改变或强化治疗方案选择",
    "changes_risk_stratification": "改变风险分层或随访策略",
    "changes_routing": "改变诊疗路径或分流",
    "closes_broad_context_source_gap_without_upgrading_evidence": "补足背景证据，但不升级疗效证据等级",
    "context_only": "背景/风险分层证据，不直接作为疗效证明",
    "discourages_use": "支持避免或限制使用",
    "exploratory_complement_branch": "支持探索性补体治疗分支",
    "no_change": "不改变当前治疗层级",
    "predictor_context": "提供疗效预测或风险因素背景",
    "refines_dose": "细化剂量方案",
    "refines_duration": "细化疗程或时机",
    "safety_boundary": "明确安全或误用边界",
    "safety_context": "提供安全性背景",
    "supports_exception_only": "仅支持例外/特殊情境使用",
    "supports_existing": "支持既有治疗方案",
    "supports_risk_stratified_followup": "支持风险分层随访",
    "permanent_boundary": "长期不推荐边界",
    "research_only": "仅限研究/观察清单",
    "misuse_boundary": "误用边界",
    "textbook_misuse_boundary": "教材对齐的误用边界",
    "not_fully_enumerated": "未完全列举",
}

PUBLIC_CARD_FIELDS = [
    "card_id",
    "disease_key",
    "regimen_id",
    "drug_ids",
    "regimen_name",
    "clinical_scenario",
    "query_sections",
    "recommendation_status",
    "dose_summary",
    "duration_summary",
    "mechanism_summary",
    "evidence_summary",
    "guideline_summary",
    "safety_summary",
    "local_status_summary",
    "evidence_drilldown",
    "guideline_drilldown",
    "source_drilldown",
    "display_language",
]

RECOMMENDATION_STATUS_LABELS = {
    "recommended": "推荐",
    "conditional": "条件性推荐",
    "alternative": "替代方案",
    "exploratory": "探索性",
    "not_recommended": "不推荐",
    "rescue_only": "仅限抢救/难治场景",
    "supportive_only": "仅支持/基础治疗",
}

HIDDEN_DISPLAY_VALUES = {"", "not_applicable", "not_available", "pending_lookup", "unknown", None}
PAGE_NOISE_PATTERNS = [
    re.compile(r"\bPDF[_ -]?PAGE[_: ]?\d{1,4}(?:\s*[-–]\s*\d{1,4})?\b", re.IGNORECASE),
    re.compile(r"\bpage[_ -]?\d{3,4}(?:\s*[-–/]\s*page[_ -]?\d{3,4})?\b", re.IGNORECASE),
    re.compile(r"\bpages?\s+\d{3,4}(?:\s*[-–/]\s*\d{3,4})?\b", re.IGNORECASE),
    re.compile(r"\bPDF\s+pages?\s+\d{1,4}(?:\s*[-–/]\s*\d{1,4})?\b", re.IGNORECASE),
    re.compile(r"\bbook\s+pages?\s+\d{3,4}(?:\s*[-–/]\s*\d{3,4})?\b", re.IGNORECASE),
    re.compile(r"\bOCR\s+(?:route|path|source|repair)\b", re.IGNORECASE),
    re.compile(r"\bOCR路径\b", re.IGNORECASE),
]
SOURCE_PROCESS_REPLACEMENTS = [
    (re.compile(r"本地中文教科书\s*/\s*OCR\s*提取(?:内容)?", re.IGNORECASE), "《肾脏病学》第四版"),
    (re.compile(r"中文教科书\s*/\s*OCR\s*提取(?:内容)?", re.IGNORECASE), "中文教科书来源"),
    (re.compile(r"OCR\s*(?:提取|抽取)(?:稿|内容)?", re.IGNORECASE), "原文提取"),
    (re.compile(r"《肾脏病学》第四版\s*OCR", re.IGNORECASE), "《肾脏病学》第四版"),
    (re.compile(r"《肾脏病学》第4版\s*OCR", re.IGNORECASE), "《肾脏病学》第四版"),
    (re.compile(r"教科书\s*OCR|教材\s*OCR|教科书页面\s*OCR", re.IGNORECASE), "《肾脏病学》第四版"),
    (re.compile(r"随机对照试验\s*PDF\s*扫描\s*OCR", re.IGNORECASE), "随机对照试验扫描版原文"),
    (re.compile(r"OCR\s*页面级核查|页面级核查", re.IGNORECASE), "原文页码级核对"),
    (re.compile(r"OCR\s*验证", re.IGNORECASE), "原文核对"),
    (
        re.compile(r"\bthe specific dosing comes from page-traced Chinese textbook OCR\b", re.IGNORECASE),
        "具体剂量来自教材来源",
    ),
    (
        re.compile(
            r"\b(?:local\s+)?(?:fourth[- ]edition|4th[- ]edition)\s+(?:nephrology\s+)?textbook\s+OCR\b",
            re.IGNORECASE,
        ),
        "教材来源",
    ),
    (
        re.compile(r"\b(?:Chinese|local)\s+textbook\s+OCR\b", re.IGNORECASE),
        "教材来源",
    ),
    (re.compile(r"\btextbook\s+OCR\b", re.IGNORECASE), "教材来源"),
    (re.compile(r"\bChinese\s+OCR\b", re.IGNORECASE), "中文来源"),
    (re.compile(r"\bThe\s+Chinese\s+OCR\b", re.IGNORECASE), "中文来源"),
    (re.compile(r"\bOCR[- ](?:checked|reviewed)\b", re.IGNORECASE), "原文核对"),
    (re.compile(r"\bOCR\s+page[- ]level\s+check\b", re.IGNORECASE), "原文页码级核对"),
    (re.compile(r"\bpage[- ]audited\b", re.IGNORECASE), "原文核对"),
    (re.compile(r"\bpage[- ]traced\b", re.IGNORECASE), "原文核对"),
    (re.compile(r"\bpage[- ]level\b", re.IGNORECASE), "原文核对"),
    (re.compile(r"(?<![A-Za-z])OCR(?![A-Za-z])", re.IGNORECASE), ""),
]

INTENT_LABELS_CN = {
    "overview": "治疗总览",
    "classic_standard": "经典/一线/基础处理",
    "new_targeted": "新药/生物制剂/靶向治疗",
    "evidence": "证据/指南/文献来源",
    "special_scenarios": "特殊场景",
    "safety_boundary": "不推荐",
    "payer_local": "医保/本地可及性",
}

INTENT_SECTION_FILTERS = {
    "classic_standard": {"supportive_foundation", "classic_regimens", "special_scenarios"},
    "new_targeted": {"new_targeted_regimens", "exploratory_regimens"},
    "special_scenarios": {"special_scenarios"},
    "safety_boundary": {"not_recommended"},
}

INTENT_KEYWORDS = {
    "new_targeted": [
        "新药",
        "新治疗",
        "生物制剂",
        "生物试剂",
        "靶向",
        "补体",
        "内皮素",
        "april",
        "baff",
        "targeted",
        "biologic",
        "novel",
    ],
    "classic_standard": [
        "经典",
        "一线",
        "基础",
        "支持",
        "常规",
        "激素",
        "免疫抑制",
        "传统",
        "standard",
        "classic",
        "first line",
    ],
    "evidence": [
        "证据",
        "文献",
        "来源",
        "研究",
        "指南",
        "rct",
        "pmid",
        "doi",
        "trial",
        "evidence",
        "guideline",
    ],
    "special_scenarios": [
        "特殊",
        "场景",
        "分型",
        "亚型",
        "病理",
        "预测",
        "疗效预测",
        "手术",
        "介入",
        "溶栓",
        "取栓",
        "支架",
        "栓塞",
        "抗凝",
        "透析",
        "移植",
        "妊娠",
        "复发",
        "难治",
        "救援",
        "抢救",
        "挽救",
        "抵抗",
        "耐药",
        "不耐受",
        "失败",
        "失败后",
        "rescue",
        "refractory",
        "resistant",
        "intolerant",
        "special",
        "subtype",
        "predictor",
    ],
    "safety_boundary": [
        "不推荐",
        "不能用",
        "能不能用",
        "能用吗",
        "可以用吗",
        "推荐吗",
        "禁用",
        "禁忌",
        "误用",
        "安全",
        "感染筛查",
        "感染风险",
        "感染监测",
        "毒性",
        "副作用",
        "妊娠",
        "not recommended",
        "recommend",
        "avoid",
        "safety",
    ],
    "payer_local": [
        "医保",
        "报销",
        "支付",
        "本地",
        "可及",
        "获批",
        "payer",
        "insurance",
    ],
}

OVERVIEW_QUERY_KEYWORDS = [
    "有哪些治疗方案",
    "治疗方案有哪些",
    "如何治疗",
    "怎么治疗",
]

SPECIAL_EXPLICIT_QUERY_KEYWORDS = [
    "特殊",
    "场景",
    "分型",
    "亚型",
    "病理",
    "预测",
    "疗效预测",
    "手术",
    "介入",
    "溶栓",
    "取栓",
    "支架",
    "抗凝",
    "透析",
    "移植",
    "妊娠",
    "复发",
    "难治",
    "救援",
    "抢救",
    "挽救",
    "抵抗",
    "耐药",
    "不耐受",
    "失败后",
]

QUERY_FILLER_PATTERNS = [
    r"有哪些治疗方案",
    r"治疗方案有哪些",
    r"如何治疗",
    r"怎么治疗",
    r"怎么用",
    r"如何用",
    r"怎么处理",
    r"处理是什么",
    r"是什么",
    r"用法",
    r"使用",
    r"用",
    r"有哪些",
    r"有没有",
    r"情况",
    r"以及",
    r"或者",
    r"还是",
    r"其中",
    r"有无",
    r"相关",
    r"这个病",
    r"该病",
    r"是否",
    r"可以用",
    r"推荐吗",
    r"推荐",
    r"关键",
    r"主要",
    r"具体",
    r"疗效",
    r"因素",
    r"因子",
    r"影响",
    r"怎么影响",
    r"剂量",
    r"疗程",
    r"方案",
    r"治疗",
    r"经典",
    r"一线",
    r"基础",
    r"支持",
    r"常规",
    r"激素",
    r"免疫抑制",
    r"药物",
    r"新药",
    r"新治疗",
    r"生物制剂",
    r"生物试剂",
    r"靶向",
    r"补体",
    r"抑制剂",
    r"证据",
    r"文献",
    r"来源",
    r"研究",
    r"指南",
    r"特殊",
    r"场景",
    r"分型",
    r"亚型",
    r"病理",
    r"预测",
    r"手术",
    r"介入",
    r"溶栓",
    r"取栓",
    r"抗凝",
    r"支架",
    r"栓塞",
    r"透析",
    r"移植",
    r"哪些",
    r"不推荐",
    r"不能用",
    r"禁用",
    r"禁忌",
    r"误用",
    r"安全",
    r"注意事项",
    r"医保",
    r"报销",
    r"支付",
    r"本地",
    r"可及",
    r"获批",
    r"\brct\b",
    r"\bpmid\b",
    r"\bdoi\b",
    r"的",
    r"有",
    r"无",
    r"和",
    r"或",
    r"与",
    r"及",
    r"\band\b",
    r"\bor\b",
    r"\bwhat\b",
    r"\bwhich\b",
    r"\bhow\b",
    r"\btreatment\b",
    r"\btherapy\b",
    r"\bregimen\b",
    r"\bclassic\b",
    r"\bstandard\b",
    r"\bfirst line\b",
    r"\bnovel\b",
    r"\btargeted\b",
    r"\bbiologic\b",
    r"\bevidence\b",
    r"\bguideline\b",
    r"\bsafety\b",
    r"\bpayer\b",
]

QUERY_BOUNDARY_PATTERNS = [
    r"有哪些治疗方案",
    r"治疗方案有哪些",
    r"怎么治疗",
    r"如何治疗",
    r"怎么用",
    r"如何用",
    r"用法",
    r"的经典",
    r"经典治疗",
    r"一线处理",
    r"有没有",
    r"新药",
    r"新治疗",
    r"生物制剂",
    r"生物试剂",
    r"靶向",
    r"医保",
    r"报销",
    r"支付",
    r"溶栓",
    r"取栓",
    r"抗凝",
    r"支架",
    r"栓塞",
    r"介入",
    r"手术",
    r"的关键",
    r"关键证据",
    r"指南来源",
    r"的特殊",
    r"特殊场景",
    r"病理分型",
    r"哪些治疗",
    r"安全注意事项",
    r"不推荐",
    r"禁忌",
]

STATUS_ORDER = {
    "recommended": 0,
    "preferred": 0,
    "required": 0,
    "supportive_only": 1,
    "conditional": 2,
    "alternative": 3,
    "rescue_only": 4,
    "exploratory": 5,
    "not_recommended": 6,
}

PREFERRED_SHORT_QUERY_REGISTRY = {
    "iga": "IgAN",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_display_translations(compiled_dir: Path) -> dict[str, Any]:
    path = compiled_dir / DISPLAY_ZH_FILENAME
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except json.JSONDecodeError:
        return {}
    return payload.get("cards") or {}


def load_evidence_digest_translations(compiled_dir: Path) -> dict[str, Any]:
    path = compiled_dir / EVIDENCE_DIGEST_ZH_FILENAME
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except json.JSONDecodeError:
        return {}
    return payload.get("evidence") or {}


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.lower()
    text = re.sub(r"[\s_－—–,，()（）/;；:：]+", " ", text)
    return text.strip()


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value))


def latin_tokens(value: Any) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", normalize_text(value)) if token}


def humanize_display_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value in DISPLAY_ENUM_LABELS:
        return DISPLAY_ENUM_LABELS[value]
    if re.fullmatch(r"[a-z]+(?:_[a-z0-9]+)+", value):
        return value.replace("_", " ")
    return value


def is_displayable(value: Any) -> bool:
    return value not in HIDDEN_DISPLAY_VALUES


def format_display_text(value: Any) -> str:
    if not is_displayable(value):
        return ""
    text = str(value)
    text = sanitize_user_facing_text(text)
    text = re.sub(r"\bnot_applicable(?:_[a-z0-9]+)*\b[;:：,， ]*", "", text)
    text = re.sub(r"\bnot_available(?:_[a-z0-9]+)*\b[;:：,， ]*", "", text)
    text = re.sub(r"\bpending_lookup(?:_[a-z0-9]+)*\b[;:：,， ]*", "", text)

    def replace_enum(match: re.Match[str]) -> str:
        token = match.group(0)
        replacement = humanize_display_value(token)
        return str(replacement)

    text = re.sub(r"\b[a-z]+(?:_[a-z0-9]+)+\b", replace_enum, text)
    return text.strip(" ;；,，")


def sanitize_user_facing_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value
    text = re.sub(r"《肾脏病学》第\s*4\s*版", "《肾脏病学》第四版", text)
    for pattern, replacement in SOURCE_PROCESS_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    for pattern in PAGE_NOISE_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"(《肾脏病学》第四版[^，。；;]*)\s*(?:已完成|完成)?(?:本地)?\s*(?:合并稿|清洗稿)?", r"\1", text)
    text = re.sub(r"\s+([,.;:，。；：])", r"\1", text)
    text = re.sub(r"([（(])\s+", r"\1", text)
    text = re.sub(r"\s+([）)])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"(《肾脏病学》第4版)\s*(?:and|plus|,|，|；|;)\s*", r"\1", text)
    text = re.sub(r"\s*(?:and|plus)\s*(?=[,.;，。；])", "", text, flags=re.IGNORECASE)
    return text.strip(" ,;:，。；：")


def sanitize_display_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_display_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_display_tree(item) for item in value]
    return sanitize_user_facing_text(value)


def display_status(status: Any) -> str:
    if isinstance(status, str):
        return RECOMMENDATION_STATUS_LABELS.get(status, str(humanize_display_value(status)))
    return str(status or "")


def display_pmid(value: Any) -> str:
    if not is_displayable(value):
        return ""
    text = str(value)
    pmids = re.findall(r"\b\d{5,10}\b", text)
    if pmids:
        return ";".join(pmids)
    if re.search(r"not_available|not_applicable|pending_lookup|not_fully_enumerated", text):
        return ""
    return format_display_text(text)


STRUCTURED_DIGEST_LABELS = {
    "research_question": "研究问题",
    "design": "设计",
    "population": "人群",
    "intervention_comparator": "干预/对照",
    "endpoint": "终点",
    "results": "结果",
    "safety": "安全",
    "treatment_impact": "治疗影响",
}


def detect_intents(query: str) -> list[str]:
    text = normalize_text(query_body_after_disease_phrase(query))
    if any(keyword in text for keyword in OVERVIEW_QUERY_KEYWORDS):
        explicit_intents = [
            intent
            for intent, keywords in INTENT_KEYWORDS.items()
            if intent != "special_scenarios"
            and any(keyword.lower() in text for keyword in keywords)
        ]
        if any(keyword in text for keyword in SPECIAL_EXPLICIT_QUERY_KEYWORDS):
            explicit_intents.append("special_scenarios")
        return explicit_intents or ["overview"]
    intents = [
        intent
        for intent, keywords in INTENT_KEYWORDS.items()
        if any(keyword.lower() in text for keyword in keywords)
    ]
    if not intents:
        return ["overview"]
    return intents


def strip_query_intent(query: str) -> str:
    text = str(query)
    for pattern in sorted(QUERY_FILLER_PATTERNS, key=len, reverse=True):
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[?？。.!！,，;；:：()（）/、]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def leading_disease_phrase(query: str) -> str:
    text = str(query)
    boundaries = [
        match.start()
        for pattern in QUERY_BOUNDARY_PATTERNS
        for match in [re.search(pattern, text, flags=re.IGNORECASE)]
        if match
    ]
    if not boundaries:
        return ""
    leading = text[: min(boundaries)]
    leading = re.sub(r"[?？。.!！,，;；:：()（）/、]+", " ", leading)
    return re.sub(r"\s+", " ", leading).strip()


def query_body_after_disease_phrase(query: str) -> str:
    text = str(query)
    boundaries = [
        match.start()
        for pattern in QUERY_BOUNDARY_PATTERNS
        for match in [re.search(pattern, text, flags=re.IGNORECASE)]
        if match
    ]
    if not boundaries:
        return text
    return text[min(boundaries) :]


def registry_query_candidates(query: str) -> list[str]:
    candidates = [str(query)]
    leading = leading_disease_phrase(query)
    if leading and leading not in candidates:
        candidates.append(leading)
        stripped_leading = strip_query_intent(leading)
        if stripped_leading and stripped_leading not in candidates:
            candidates.append(stripped_leading)
        normalized_leading = normalize_text(leading)
        if normalized_leading and normalized_leading not in candidates:
            candidates.append(normalized_leading)
        normalized_stripped_leading = normalize_text(stripped_leading)
        if normalized_stripped_leading and normalized_stripped_leading not in candidates:
            candidates.append(normalized_stripped_leading)
        return candidates
    stripped = strip_query_intent(query)
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    normalized = normalize_text(stripped)
    if normalized and normalized not in candidates:
        candidates.append(normalized)
    return candidates


def augment_registry_search_text(
    row: dict[str, Any],
    diseases_by_key: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    if not diseases_by_key:
        return row
    extras: list[str] = []
    for module_key in row.get("treatment_modules") or [row.get("treatment_module")]:
        disease = diseases_by_key.get(module_key)
        if not disease:
            continue
        extras.extend(
            [
                disease.get("disease_key"),
                disease.get("disease_id"),
                disease.get("name_cn"),
                disease.get("name_en"),
            ]
        )
        extras.extend(disease.get("aliases") or [])
    if not extras:
        return row
    augmented = dict(row)
    augmented["search_text"] = " ".join(
        str(item)
        for item in [row.get("search_text"), *extras]
        if item
    )
    return augmented


def registry_match_score(query: str, row: dict[str, Any]) -> int:
    q_norm = normalize_text(query)
    q_compact = compact_text(query)
    q_tokens = latin_tokens(query)
    is_short_latin = bool(re.fullmatch(r"[a-z0-9]{2,4}", q_norm))
    preferred_registry = PREFERRED_SHORT_QUERY_REGISTRY.get(q_norm)
    if preferred_registry and row.get("registry_id") == preferred_registry:
        return 99

    direct_names = [
        row.get("registry_id"),
        row.get("requested_name"),
        row.get("normalized_key"),
    ]
    alias_names = row.get("query_aliases") or []
    routed_names = [row.get("treatment_module"), *(row.get("treatment_modules") or [])]
    names = [*direct_names, *alias_names, *routed_names]
    direct_norm = [normalize_text(name) for name in direct_names if name]
    direct_compact = [compact_text(name) for name in direct_names if name]
    direct_tokens = set().union(*(latin_tokens(name) for name in direct_names if name)) if direct_names else set()
    alias_norm = [normalize_text(name) for name in alias_names if name]
    alias_compact = [compact_text(name) for name in alias_names if name]
    alias_tokens = set().union(*(latin_tokens(name) for name in alias_names if name)) if alias_names else set()
    routed_norm = [normalize_text(name) for name in routed_names if name]
    routed_compact = [compact_text(name) for name in routed_names if name]
    routed_tokens = set().union(*(latin_tokens(name) for name in routed_names if name)) if routed_names else set()
    names_norm = [normalize_text(name) for name in names if name]
    names_compact = [compact_text(name) for name in names if name]

    if q_norm in direct_norm or q_compact in direct_compact:
        return 100
    if q_norm in alias_norm or q_compact in alias_compact:
        return 98
    if is_short_latin and q_norm in alias_tokens:
        return 96
    if is_short_latin and q_norm in direct_tokens:
        return 95
    if q_norm in routed_norm or q_compact in routed_compact:
        return 82
    if is_short_latin and q_norm in routed_tokens:
        return 78
    if any(q_compact and q_compact in item for item in names_compact):
        return 85
    if any(item and len(item) >= 3 and item in q_compact for item in names_compact):
        return 84

    search_text = row.get("search_text") or ""
    search_norm = normalize_text(search_text)
    search_compact = compact_text(search_text)
    search_tokens = latin_tokens(search_text)
    if is_short_latin:
        return 70 if q_norm in search_tokens else 0

    if q_compact and q_compact in search_compact:
        return 70
    terms = [term for term in q_norm.split() if term]
    if terms and all(term in search_norm for term in terms):
        return 60
    return 0


def find_registry_matches(
    query: str,
    registry: list[dict[str, Any]],
    limit: int = 8,
    diseases_by_key: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for row in registry:
        augmented = augment_registry_search_text(row, diseases_by_key)
        score, specificity = max(
            (
                registry_match_score(candidate, augmented),
                len(compact_text(candidate)),
            )
            for candidate in registry_query_candidates(query)
        )
        if score >= 60:
            scored.append((score, specificity, row))
    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            0 if item[2].get("is_compiled_query_ready") else 1,
            str(item[2].get("requested_name") or item[2].get("registry_id")),
        )
    )
    return [dict(row, match_score=score) for score, _, row in scored[:limit]]


def card_matches_intent(card: dict[str, Any], intents: list[str]) -> bool:
    filters: set[str] = set()
    for intent in intents:
        filters.update(INTENT_SECTION_FILTERS.get(intent, set()))
    if not filters:
        return True
    sections = set(card.get("query_sections") or ["special_scenarios"])
    return bool(sections & filters)


def card_sort_key(card: dict[str, Any]) -> tuple[int, int, str]:
    sections = card.get("query_sections") or ["special_scenarios"]
    section_rank = min(SECTION_ORDER.get(section, 99) for section in sections)
    status_rank = STATUS_ORDER.get(card.get("recommendation_status"), 9)
    return section_rank, status_rank, str(card.get("regimen_name") or card.get("regimen_id"))


def summarize_evidence(card: dict[str, Any], max_items: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for study in card.get("evidence_studies") or []:
        structured_summary = study.get("structured_summary_cn")
        if not isinstance(structured_summary, dict) or not any(structured_summary.values()):
            structured_summary = derive_evidence_digest(study)
        items.append(
            {
                "study_id": study.get("study_id"),
                "study_name": sanitize_user_facing_text(study.get("study_name")),
                "design": humanize_display_value(study.get("study_design")),
                "pmid": study.get("pmid"),
                "doi": study.get("doi"),
                "structured_summary_cn": sanitize_display_tree(structured_summary),
                "result_summary": sanitize_user_facing_text(study.get("result_summary")),
                "treatment_impact": humanize_display_value(study.get("treatment_impact")),
            }
        )
        if len(items) >= max_items:
            break
    return items


def first_display_text(*values: Any) -> str:
    for value in values:
        text = sanitize_user_facing_text(humanize_display_value(value))
        if is_displayable(text):
            return str(text)
    return ""


def derive_evidence_digest(study: dict[str, Any]) -> dict[str, str]:
    intervention = first_display_text(study.get("intervention"))
    comparator = first_display_text(study.get("comparator"))
    intervention_comparator = ""
    if intervention and comparator:
        intervention_comparator = f"干预：{intervention}；对照：{comparator}"
    elif intervention:
        intervention_comparator = f"干预：{intervention}"
    elif comparator:
        intervention_comparator = f"对照/参照：{comparator}"

    title = first_display_text(study.get("title"), study.get("study_name"))
    research_question = title
    if intervention_comparator and first_display_text(study.get("population")):
        research_question = f"在{first_display_text(study.get('population'))}中评估{intervention_comparator}的治疗价值"
    elif intervention_comparator:
        research_question = f"评估{intervention_comparator}的治疗价值"

    safety = first_display_text(study.get("safety_summary"))
    if not safety:
        safety = "当前结构化记录未提取到单独安全摘要；需结合原文不良事件表和方案安全监测。"

    return {
        "research_question": research_question,
        "design": first_display_text(study.get("study_design"), study.get("evidence_tier")),
        "population": first_display_text(study.get("population")),
        "intervention_comparator": intervention_comparator,
        "endpoint": first_display_text(study.get("primary_endpoint")),
        "results": first_display_text(study.get("result_summary")),
        "safety": safety,
        "treatment_impact": first_display_text(study.get("treatment_impact")),
    }


def summarize_guidelines(card: dict[str, Any], max_items: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for guideline in card.get("guideline_recommendations") or []:
        items.append(
            {
                "guideline_id": guideline.get("guideline_id"),
                "organization": sanitize_user_facing_text(guideline.get("organization")),
                "year": guideline.get("year"),
                "grade": humanize_display_value(guideline.get("grade")),
                "recommendation_text": sanitize_user_facing_text(guideline.get("recommendation_text")),
            }
        )
        if len(items) >= max_items:
            break
    return items


def summarize_sources(card: dict[str, Any], max_items: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    direct_source_ids = [str(source_id) for source_id in card.get("direct_source_ids") or []]
    sources = card.get("sources") or []
    if direct_source_ids:
        source_order = {source_id: index for index, source_id in enumerate(direct_source_ids)}
        sources = [
            source
            for source in sources
            if str(source.get("source_id")) in source_order
        ]
        sources = sorted(sources, key=lambda source: source_order[str(source.get("source_id"))])
    for source in sources:
        items.append(
            {
                "source_id": source.get("source_id"),
                "source_type": sanitize_user_facing_text(source.get("source_type")),
                "title": sanitize_user_facing_text(source.get("title")),
                "date_or_year": source.get("date_or_year"),
                "pmid": source.get("pmid"),
                "doi": source.get("doi"),
            }
        )
        if len(items) >= max_items:
            break
    return items


def public_card_summary(card: dict[str, Any]) -> dict[str, Any]:
    summary = {field: card.get(field) for field in PUBLIC_CARD_FIELDS if field in card}
    summary["is_public_card"] = True
    summary.setdefault("query_sections", [])
    summary.setdefault("evidence_drilldown", [])
    summary.setdefault("guideline_drilldown", [])
    summary.setdefault("source_drilldown", [])
    cleaned = sanitize_display_tree(summary)
    for field in [
        "clinical_scenario",
        "dose_summary",
        "duration_summary",
        "mechanism_summary",
        "evidence_summary",
        "guideline_summary",
        "safety_summary",
        "local_status_summary",
    ]:
        if not is_displayable(cleaned.get(field)):
            cleaned[field] = ""
    return cleaned


def apply_display_translation(summary: dict[str, Any], translated: dict[str, Any] | None) -> dict[str, Any]:
    if not translated:
        return summary
    fields = translated.get("fields") or {}
    for field in [
        "regimen_name",
        "clinical_scenario",
        "dose_summary",
        "duration_summary",
        "mechanism_summary",
        "evidence_summary",
        "guideline_summary",
        "safety_summary",
        "local_status_summary",
    ]:
        value = fields.get(field)
        if is_displayable(value):
            summary[field] = value

    evidence_by_id = {row.get("study_id"): row for row in translated.get("evidence") or []}
    for item in summary.get("evidence_drilldown") or []:
        translated_item = evidence_by_id.get(item.get("study_id"))
        if not translated_item:
            continue
        for field in ["study_name", "design", "structured_summary_cn", "result_summary", "treatment_impact"]:
            value = translated_item.get(field)
            if is_displayable(value):
                item[field] = value

    guideline_by_id = {row.get("guideline_key"): row for row in translated.get("guidelines") or []}
    for item in summary.get("guideline_drilldown") or []:
        translated_item = guideline_by_id.get(item.get("guideline_id"))
        if not translated_item:
            continue
        for field in ["organization", "grade", "recommendation_text"]:
            value = translated_item.get(field)
            if is_displayable(value):
                item[field] = value

    source_by_id = {row.get("source_key"): row for row in translated.get("sources") or []}
    for item in summary.get("source_drilldown") or []:
        translated_item = source_by_id.get(item.get("source_id"))
        if not translated_item:
            continue
        for field in ["source_type", "title"]:
            value = translated_item.get(field)
            if is_displayable(value):
                item[field] = value
    summary["display_language"] = "zh-CN"
    return summary


def apply_evidence_digest_translation(summary: dict[str, Any], evidence_translations: dict[str, Any] | None) -> None:
    if not evidence_translations:
        return
    disease_key = summary.get("disease_key")
    for item in summary.get("evidence_drilldown") or []:
        study_id = item.get("study_id")
        translated = evidence_translations.get(f"{disease_key}:{study_id}") or evidence_translations.get(str(study_id))
        if not translated:
            continue
        for field in ["study_name", "design", "structured_summary_cn", "result_summary", "treatment_impact"]:
            value = translated.get(field)
            if isinstance(value, dict) or is_displayable(value):
                item[field] = sanitize_display_tree(value)


def slim_card(
    card: dict[str, Any],
    display_translations: dict[str, Any] | None = None,
    evidence_translations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if card.get("is_public_card"):
        return public_card_summary(card)

    summary = {
        "card_id": card.get("card_id"),
        "disease_key": card.get("disease_key"),
        "regimen_id": card.get("regimen_id"),
        "regimen_name": card.get("regimen_name"),
        "clinical_scenario": card.get("clinical_scenario"),
        "query_sections": card.get("query_sections") or [],
        "recommendation_status": card.get("recommendation_status"),
        "dose_summary": card.get("dose_summary"),
        "duration_summary": card.get("duration_summary"),
        "mechanism_summary": card.get("mechanism_summary"),
        "evidence_summary": card.get("evidence_summary"),
        "guideline_summary": card.get("guideline_summary"),
        "safety_summary": card.get("safety_summary"),
        "local_status_summary": card.get("local_status_summary"),
        "qa": {
            "entity_ready_status": (card.get("qa") or {}).get("entity_ready_status"),
            "entity_open_blocker_count": (card.get("qa") or {}).get("entity_open_blocker_count"),
            "disease_query_ready_status": (card.get("qa") or {}).get("disease_query_ready_status"),
        },
        "evidence_drilldown": summarize_evidence(card),
        "guideline_drilldown": summarize_guidelines(card),
        "source_drilldown": summarize_sources(card),
    }
    translated = (display_translations or {}).get(summary["card_id"])
    summary = apply_display_translation(summary, translated)
    apply_evidence_digest_translation(summary, evidence_translations)
    cleaned = sanitize_display_tree(summary)
    for field in [
        "clinical_scenario",
        "dose_summary",
        "duration_summary",
        "mechanism_summary",
        "evidence_summary",
        "guideline_summary",
        "safety_summary",
        "local_status_summary",
    ]:
        if not is_displayable(cleaned.get(field)):
            cleaned[field] = ""
    return cleaned


def empty_intent_message(result: dict[str, Any], module: dict[str, Any]) -> str:
    intents = set(result.get("detected_intents") or [])
    labels = [
        SECTION_LABELS_CN.get(section, section)
        for section in module.get("available_sections", [])
    ]
    suffix = f"；该病种已有分层：{'、'.join(labels)}" if labels else ""
    if "new_targeted" in intents:
        return f"当前治疗包没有结构化的新药/生物制剂/靶向治疗卡{suffix}。"
    if "special_scenarios" in intents:
        return f"当前治疗包没有单独结构化的特殊场景、病理分型或疗效预测治疗卡{suffix}。"
    if "safety_boundary" in intents:
        return f"当前治疗包没有单独结构化的不推荐治疗方案；请结合各方案的安全摘要和监测要求{suffix}。"
    if "payer_local" in intents:
        return f"当前治疗包没有可展示的中国医保/本地可及性条目{suffix}。"
    return f"当前治疗包没有与该问题意图直接匹配的治疗卡{suffix}。"


def query_treatment(
    query: str,
    compiled_dir: Path = DEFAULT_COMPILED_DIR,
    registry_limit: int = 8,
    card_limit_per_module: int | None = None,
) -> dict[str, Any]:
    registry = load_json(compiled_dir / "disease_registry.json")
    diseases = load_json(compiled_dir / "diseases.json")
    cards = load_json(compiled_dir / "treatment_cards.json")
    display_translations = load_display_translations(compiled_dir)
    evidence_translations = load_evidence_digest_translations(compiled_dir)
    diseases_by_key = {row["disease_key"]: row for row in diseases}
    detected_intents = detect_intents(query)
    matches = find_registry_matches(query, registry, limit=registry_limit, diseases_by_key=diseases_by_key)

    cards_by_disease: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        cards_by_disease.setdefault(card["disease_key"], []).append(card)
    for disease_cards in cards_by_disease.values():
        disease_cards.sort(key=card_sort_key)

    modules: list[dict[str, Any]] = []
    seen_modules: set[str] = set()
    for match in matches[:1]:
        treatment_modules = match.get("treatment_modules") or []
        if not treatment_modules and match.get("treatment_module"):
            treatment_modules = [match["treatment_module"]]
        for module_key in treatment_modules:
            if module_key in seen_modules:
                continue
            seen_modules.add(module_key)
            all_module_cards = cards_by_disease.get(module_key, [])
            module_cards = [card for card in all_module_cards if card_matches_intent(card, detected_intents)]
            if not module_cards and "safety_boundary" in detected_intents:
                module_cards = [
                    card
                    for card in all_module_cards
                    if card.get("safety_summary") or card.get("local_status_summary")
                ]
            if card_limit_per_module is not None:
                module_cards = module_cards[:card_limit_per_module]
            grouped: dict[str, list[dict[str, Any]]] = {}
            for card in module_cards:
                sections = card.get("query_sections") or ["special_scenarios"]
                section = min(sections, key=lambda item: SECTION_ORDER.get(item, 99))
                grouped.setdefault(section, []).append(slim_card(card, display_translations, evidence_translations))
            modules.append(
                {
                    "module_key": module_key,
                    "card_count": len(all_module_cards),
                    "filtered_card_count": len(module_cards),
                    "available_sections": sorted(
                        {
                            section
                            for card in all_module_cards
                            for section in (card.get("query_sections") or ["special_scenarios"])
                        },
                        key=lambda item: SECTION_ORDER.get(item, 99),
                    ),
                    "sections": [
                        {
                            "query_section": section,
                            "label_cn": SECTION_LABELS_CN.get(section, section),
                            "cards": grouped.get(section, []),
                        }
                        for section in sorted(grouped, key=lambda item: SECTION_ORDER.get(item, 99))
                    ],
                }
            )

    return {
        "query": query,
        "detected_intents": detected_intents,
        "detected_intent_labels": [INTENT_LABELS_CN.get(intent, intent) for intent in detected_intents],
        "matches": [
            {
                "registry_id": row.get("registry_id"),
                "requested_name": row.get("requested_name"),
                "coverage_status": row.get("coverage_status"),
                "match_score": row.get("match_score"),
                "treatment_module": row.get("treatment_module"),
                "treatment_modules": row.get("treatment_modules") or [],
                "is_compiled_query_ready": row.get("is_compiled_query_ready"),
            }
            for row in matches
        ],
        "selected_registry": matches[0].get("registry_id") if matches else None,
        "is_fanout": bool(matches and len(matches[0].get("treatment_modules") or []) > 1),
        "modules": modules,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# 查询：{result['query']}")
    if not result["matches"]:
        lines.append("")
        lines.append("未匹配到 query-ready 病种入口。")
        return "\n".join(lines)

    selected = result["matches"][0]
    lines.append("")
    lines.append(
        f"匹配：{selected['requested_name']} / `{selected['registry_id']}` / `{selected['coverage_status']}`"
    )
    if result.get("detected_intent_labels"):
        lines.append(f"问题意图：{'、'.join(result['detected_intent_labels'])}")
    if result.get("is_fanout"):
        lines.append("")
        lines.append("这是合并入口，已展开以下治疗模块：")
        for module in selected.get("treatment_modules") or []:
            lines.append(f"- `{module}`")

    for module in result["modules"]:
        lines.append("")
        lines.append(
            f"## {module['module_key']} "
            f"({module.get('filtered_card_count', 0)}/{module.get('card_count', 0)} cards)"
        )
        if not module["sections"]:
            lines.append("")
            lines.append(empty_intent_message(result, module))
            continue
        for section in module["sections"]:
            lines.append("")
            lines.append(f"### {section['label_cn']} (`{section['query_section']}`)")
            for card in section["cards"]:
                lines.append(f"- **{card['regimen_name']}** [{display_status(card.get('recommendation_status'))}]")
                dose_text = format_display_text(card.get("dose_summary"))
                duration_text = format_display_text(card.get("duration_summary"))
                evidence_text = format_display_text(card.get("evidence_summary"))
                guideline_text = format_display_text(card.get("guideline_summary"))
                mechanism_text = format_display_text(card.get("mechanism_summary"))
                safety_text = format_display_text(card.get("safety_summary"))
                local_text = format_display_text(card.get("local_status_summary"))
                if dose_text:
                    lines.append(f"  - 剂量/疗程：{dose_text}")
                if duration_text and duration_text != dose_text:
                    lines.append(f"  - 疗程/时机：{duration_text}")
                if evidence_text:
                    lines.append(f"  - 证据：{evidence_text}")
                if guideline_text:
                    lines.append(f"  - 指南：{guideline_text}")
                if mechanism_text:
                    lines.append(f"  - 机制：{mechanism_text}")
                if "safety_boundary" in result.get("detected_intents", []) and safety_text:
                    lines.append(f"  - 安全监测：{safety_text}")
                if "payer_local" in result.get("detected_intents", []) and local_text:
                    lines.append(f"  - 医保/本地：{local_text}")
                evidence = card.get("evidence_drilldown") or []
                guidelines = card.get("guideline_drilldown") or []
                sources = card.get("source_drilldown") or []
                if "evidence" in result.get("detected_intents", []):
                    for item in evidence[:2]:
                        label = item.get("study_name") or item.get("study_id") or "evidence"
                        bits = []
                        design = format_display_text(item.get("design"))
                        if design:
                            bits.append(design)
                        pmid = display_pmid(item.get("pmid"))
                        if pmid:
                            bits.append(f"PMID {pmid}")
                        prefix = f"  - 研究：{label}"
                        if bits:
                            prefix += f" ({'; '.join(bits)})"
                        lines.append(prefix)
                        structured_summary = item.get("structured_summary_cn") or {}
                        if isinstance(structured_summary, dict):
                            for key, label_cn in STRUCTURED_DIGEST_LABELS.items():
                                digest_text = format_display_text(structured_summary.get(key))
                                if digest_text:
                                    lines.append(f"    - {label_cn}：{digest_text}")
                        result_summary = format_display_text(item.get("result_summary"))
                        treatment_impact = format_display_text(item.get("treatment_impact"))
                        if result_summary and not structured_summary:
                            lines.append(f"    - 主要结果：{result_summary}")
                        if treatment_impact and not (
                            isinstance(structured_summary, dict) and structured_summary.get("treatment_impact")
                        ):
                            lines.append(f"    - 治疗影响：{treatment_impact}")
                    for guideline in guidelines[:2]:
                        label = " ".join(
                            str(item)
                            for item in [guideline.get("organization"), guideline.get("year")]
                            if item
                        ) or guideline.get("guideline_id") or "Guideline"
                        grade = format_display_text(guideline.get("grade"))
                        suffix = f" [{grade}]" if grade else ""
                        lines.append(f"  - 指南来源：{label}{suffix}")
                        recommendation_text = format_display_text(guideline.get("recommendation_text"))
                        if recommendation_text:
                            lines.append(f"    - 推荐要点：{recommendation_text}")
                    if not evidence and not guidelines and sources:
                        first = sources[0]
                        label = first.get("title") or first.get("source_id") or "source"
                        lines.append(f"  - 来源：{label}")
                elif evidence:
                    first = evidence[0]
                    label = first.get("study_name") or first.get("study_id") or "evidence"
                    pmid = display_pmid(first.get("pmid"))
                    suffix = f" PMID {pmid}" if pmid else ""
                    lines.append(f"  - 来源示例：{label}{suffix}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the compiled renal treatment index.")
    parser.add_argument("query", help="Disease name, abbreviation, alias, or registry key.")
    parser.add_argument("--compiled-dir", type=Path, default=DEFAULT_COMPILED_DIR)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--limit-cards", type=int, default=None, help="Limit cards per module.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = query_treatment(args.query, args.compiled_dir, card_limit_per_module=args.limit_cards)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
