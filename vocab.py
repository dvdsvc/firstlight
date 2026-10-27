"""
受控词表 + FSM 黑名单约束
从 geochron_pipeline_v3 复制，用于：
1. Round 2c prompt 注入（选项列表）
2. 抽取后 Python 校验（黑名单过滤）
"""
from __future__ import annotations


# ═══════════════════════════════════════════════════
# 词表（与 pipeline v3 instructor.py Literal 类型一致）
# ═══════════════════════════════════════════════════

DATING_MINERAL_OPTIONS = [
    "Allanite", "Amphibole", "Apatite", "Baddeleyite", "Bastnaesite",
    "Biotite", "Hematite", "K-feldspar", "Matrix", "Microlite",
    "Monazite", "Muscovite", "Olivine", "Perovskite", "Plagioclase",
    "Polycrase", "Pyroxene", "Rutile", "Sanidine", "Thorite",
    "Titanite", "Uraninite", "Whole rock", "Xenotime", "Zircon",
]

ISOTOPE_SYSTEM_OPTIONS = [
    "U-Th-Pb dating", "Rb-Sr dating", "Sm-Nd dating", "Lu-Hf dating",
    "Re-Os dating", "K-Ar dating", "Ar-Ar dating", "U-Th/He dating",
    "Major element analysis", "Trace element analysis",
    "Rb-Sr isotopic analysis", "Sm-Nd isotopic analysis",
    "Pb isotopic analysis", "Lu-Hf isotopic analysis",
    "Re-Os isotopic analysis", "O isotopic analysis",
    "H isotopic analysis", "Li isotopic analysis",
    "B isotopic analysis", "C isotopic analysis",
    "N isotopic analysis", "Mg isotopic analysis",
    "Si isotopic analysis", "S isotopic analysis",
]

DATING_TECHNIQUE_OPTIONS = [
    "CAMECA SIMS", "EPMA", "ID-TIMS", "LA-ICPMS",
    "MC-ICPMS", "Q-ICPMS", "SHRIMP", "TIMS", "XRF", "Other",
]

AGE_INTERPRETATION_OPTIONS = [
    "Crystallization age", "Eruption age", "Metamorphic age",
    "Cooling age", "Mineralization/Alteration age", "Inherited age",
    "Detrital age", "Maximum Depositional Age", "Invalid/Rejected",
]

PHYSICAL_METHOD_OPTIONS = [
    "Bulk Fusion", "Single-grain Fusion",
    "Step-heating", "Ablation / Spot",
]

STATISTICAL_MODEL_OPTIONS = [
    "Single analysis age", "Apparent age", "Weighted average age",
    "Isochron age / Inverse isochron age", "Plateau age",
    "Concordia age", "Upper / Lower intercept age", "Model age",
]

DISTRIBUTION_STATE_OPTIONS = ["Peak age", "Minimum apparent age"]

ERROR_SCALE_OPTIONS = ["1σ", "2σ", "未声明"]

# 前 8 项是放射性定年体系
DATING_SYSTEMS = ISOTOPE_SYSTEM_OPTIONS[:8]


# ═══════════════════════════════════════════════════
# 文档白名单 → 黑名单链（逻辑与 fsm_constraints.py 一致）
# ═══════════════════════════════════════════════════

_DOC_MINERAL_ALLOWED = {
    "Amphibole": ["K-Ar dating", "Ar-Ar dating"],
    "Apatite": ["Rb-Sr dating", "U-Th/He dating"],
    "Monazite": ["U-Th-Pb dating"],
    "Titanite": ["U-Th-Pb dating", "U-Th/He dating"],
    "Whole rock": ["K-Ar dating", "Ar-Ar dating", "Sm-Nd dating", "Lu-Hf dating"],
    "Zircon": ["U-Th-Pb dating", "U-Th/He dating"],
}

_DOC_TECHNIQUE_ALLOWED = {
    "CAMECA SIMS": ["U-Th-Pb dating"],
    "ID-TIMS": ["U-Th-Pb dating"],
    "LA-ICPMS": ["U-Th-Pb dating"],
    "MC-ICPMS": ["Rb-Sr dating", "Sm-Nd dating", "Re-Os dating", "Lu-Hf dating"],
    "Q-ICPMS": ["Rb-Sr dating", "U-Th/He dating"],
    "SHRIMP": ["U-Th-Pb dating"],
    "TIMS": ["Rb-Sr dating", "Sm-Nd dating", "Re-Os dating"],
}

_DOC_AGE_INTERPRETATION_ALLOWED = {
    "Crystallization age": DATING_SYSTEMS,
    "Metamorphic age": DATING_SYSTEMS,
    "Cooling age": DATING_SYSTEMS,
    "Inherited age": DATING_SYSTEMS,
}

_DOC_PHYSICAL_ALLOWED = {
    "Single-grain Fusion": ["Ar-Ar dating", "U-Th/He dating"],
    "Step-heating": ["K-Ar dating", "Ar-Ar dating"],
    "Ablation / Spot": ["U-Th-Pb dating", "Ar-Ar dating", "U-Th/He dating"],
}

_DOC_STAT_ALLOWED = {
    "Isochron age / Inverse isochron age": [
        "U-Th-Pb dating", "Rb-Sr dating", "Sm-Nd dating", "Re-Os dating",
        "Lu-Hf dating", "K-Ar dating", "Ar-Ar dating",
    ],
    "Plateau age": ["Ar-Ar dating"],
    "Concordia age": ["U-Th-Pb dating"],
    "Model age": ["Re-Os dating"],
}

_DOC_DISTRIBUTION_ALLOWED: dict[str, list[str]] = {}


def _flatten_doc_terms_by_system() -> dict[str, set[str]]:
    flattened = {system: set() for system in DATING_SYSTEMS}
    for mapping in (
        _DOC_MINERAL_ALLOWED,
        _DOC_TECHNIQUE_ALLOWED,
        _DOC_AGE_INTERPRETATION_ALLOWED,
        _DOC_PHYSICAL_ALLOWED,
        _DOC_STAT_ALLOWED,
        _DOC_DISTRIBUTION_ALLOWED,
    ):
        for term, systems in mapping.items():
            for system in systems:
                if system in flattened:
                    flattened[system].add(term)
    return flattened


SYSTEM_FLAT_DOC_TERMS = _flatten_doc_terms_by_system()
GLOBAL_FLAT_DOC_TERM_SET = set().union(*SYSTEM_FLAT_DOC_TERMS.values())
SYSTEM_FLAT_BLACKLIST_CHAIN = {
    system: sorted(GLOBAL_FLAT_DOC_TERM_SET - terms)
    for system, terms in SYSTEM_FLAT_DOC_TERMS.items()
}


def _flat_blacklist_for_field(options: list[str]) -> dict[str, list[str]]:
    return {
        system: [option for option in options if option in SYSTEM_FLAT_BLACKLIST_CHAIN[system]]
        for system in DATING_SYSTEMS
    }


MINERAL_SYSTEM_BLACKLIST = _flat_blacklist_for_field(DATING_MINERAL_OPTIONS)
TECHNIQUE_SYSTEM_BLACKLIST = _flat_blacklist_for_field(DATING_TECHNIQUE_OPTIONS)
AGE_INTERPRETATION_SYSTEM_BLACKLIST = _flat_blacklist_for_field(AGE_INTERPRETATION_OPTIONS)
PHYS_SYSTEM_BLACKLIST = _flat_blacklist_for_field(PHYSICAL_METHOD_OPTIONS)
STAT_SYSTEM_BLACKLIST = _flat_blacklist_for_field(STATISTICAL_MODEL_OPTIONS)
DIST_SYSTEM_BLACKLIST = _flat_blacklist_for_field(DISTRIBUTION_STATE_OPTIONS)


def compute_constraints(isotope_system: str | None) -> dict:
    """
    给定 isotope_system，返回所有受控字段的合法选项。
    黑名单里有的项：严格过滤；没有的项：默认放行。
    """
    iso = (isotope_system or "").strip()

    def _allowed(options: list[str], field_blacklist: dict[str, list[str]]) -> list[str]:
        return [option for option in options if option not in field_blacklist.get(iso, [])]

    return {
        "allowed_dating_mineral": _allowed(DATING_MINERAL_OPTIONS, MINERAL_SYSTEM_BLACKLIST),
        "allowed_dating_technique": _allowed(DATING_TECHNIQUE_OPTIONS, TECHNIQUE_SYSTEM_BLACKLIST),
        "allowed_age_interpretation": _allowed(
            AGE_INTERPRETATION_OPTIONS, AGE_INTERPRETATION_SYSTEM_BLACKLIST
        ),
        "allowed_physical_method": _allowed(PHYSICAL_METHOD_OPTIONS, PHYS_SYSTEM_BLACKLIST),
        "allowed_statistical_model": _allowed(STATISTICAL_MODEL_OPTIONS, STAT_SYSTEM_BLACKLIST),
        "allowed_distribution_state": _allowed(
            DISTRIBUTION_STATE_OPTIONS, DIST_SYSTEM_BLACKLIST
        ),
    }
