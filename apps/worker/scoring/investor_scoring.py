from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# Жанровая модель риска (content-heavy coefficient)
GENRE_COEFFICIENTS = {
    "puzzle": 0.8,
    "platformer": 1.0,
    "roguelike": 1.0,
    "roguelite": 1.0,
    "metroidvania": 1.2,
    "horror": 1.0,
    "survival": 1.4,
    "builder": 1.4,
    "city builder": 1.4,
    "tactics": 1.5,
    "strategy": 1.6,
    "rpg": 1.8,
    "jrpg": 1.8,
    "open world": 2.2,
    "open-world": 2.2,
    "mmo": 3.0,
    "mmorpg": 3.0,
}


def clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class InvestorScoreResult:
    """Результат инвесторской оценки"""
    
    # Legacy compatibility
    legacy_score: float
    legacy_verdict: str
    
    # NEW: Investor layers
    product_potential: float
    product_confidence: str
    product_reasons: List[str]
    
    gtm_execution: float
    gtm_confidence: str
    gtm_reasons: List[str]
    
    team_delivery: float
    team_confidence: str
    team_reasons: List[str]
    
    potential_gap: float
    fixability_score: float
    fixability_breakdown: Dict[str, float]
    
    investment_profile: str
    flags: List[Dict[str, Any]]
    
    # Explanations
    fixable_weaknesses: List[str]
    investor_actions: List[str]
    decision_summary: str


def score_pitch_investor(pitch_dict: Dict[str, Any]) -> InvestorScoreResult:
    """
    Инвесторский скоринг: фокус на GAP и Fixability
    """
    
    # A) Product Potential
    pp, pp_conf, pp_reasons = _score_product_potential(pitch_dict)
    
    # B) GTM Execution
    gtm, gtm_conf, gtm_reasons = _score_gtm_execution(pitch_dict)
    
    # C) Team Delivery
    team, team_conf, team_reasons = _score_team_delivery(pitch_dict)
    
    # D) Flags
    flags = _detect_flags(pitch_dict, pp, gtm, team)
    
    # E) Gap & Fixability
    gap = pp - gtm
    fix, fix_bd = _calculate_fixability(pitch_dict, pp, gtm, team, flags)
    
    # F) Investment Profile
    profile = _determine_investment_profile(pp, gtm, team, gap, fix, flags, team_conf)
    
    # G) Explanations
    weaknesses = _identify_fixable_weaknesses(pitch_dict, gtm, fix_bd)
    actions = _generate_investor_actions(weaknesses, profile, pitch_dict)
    summary = _generate_decision_summary(profile, pp, gap, fix, flags)
    
    # Legacy compatibility
    legacy_score = _compute_legacy_score(pp, gtm, team, flags)
    legacy_verdict = _verdict_from_score(legacy_score, flags)
    
    return InvestorScoreResult(
        legacy_score=legacy_score,
        legacy_verdict=legacy_verdict,
        product_potential=pp,
        product_confidence=pp_conf,
        product_reasons=pp_reasons,
        gtm_execution=gtm,
        gtm_confidence=gtm_conf,
        gtm_reasons=gtm_reasons,
        team_delivery=team,
        team_confidence=team_conf,
        team_reasons=team_reasons,
        potential_gap=gap,
        fixability_score=fix,
        fixability_breakdown=fix_bd,
        investment_profile=profile,
        flags=flags,
        fixable_weaknesses=weaknesses,
        investor_actions=actions,
        decision_summary=summary,
    )


def _score_product_potential(pitch: Dict[str, Any]) -> tuple[float, str, List[str]]:
    """A) Можно ли это продать в принципе? (0-10)"""
    score = 5.0
    reasons = []
    
    tags = pitch.get("tags", [])
    pitch_text = pitch.get("pitch_text", "")
    build = pitch.get("build_link")
    
    # 1. Коммерческий жанр (+0 to +2)
    genre_score = _evaluate_genre_viability(tags)
    score += genre_score
    if genre_score >= 1.5:
        reasons.append(f"Strong commercial genre")
    elif genre_score < 0.5:
        reasons.append(f"Niche genre")
    
    # 2. Наличие билда (+1)
    if build:
        score += 1.0
        reasons.append("Playable build available")
    
    # 3. Читаемость core loop (+0 to +2)
    loop_clarity = _evaluate_core_loop_clarity(pitch_text, tags)
    score += loop_clarity
    if loop_clarity >= 1.5:
        reasons.append("Clear core gameplay loop")
    elif loop_clarity < 0.7:
        reasons.append("Vague gameplay description")
    
    # 4. Визуальная презентация (+0 to +1)
    video = pitch.get("video_link")
    if video:
        score += 1.0
        reasons.append("Gameplay video available")
    
    score = clamp(score, 0.0, 10.0)
    
    # Confidence
    conf = "medium"
    if build and video:
        conf = "high"
    elif not build and not video:
        conf = "low"
    
    return score, conf, reasons


def _score_gtm_execution(pitch: Dict[str, Any]) -> tuple[float, str, List[str]]:
    """B) Насколько хорошо команда продаёт? (0-10)"""
    score = 5.0
    reasons = []
    
    hook = pitch.get("hook_one_liner", "")
    pitch_text = pitch.get("pitch_text", "")
    tags = pitch.get("tags", [])
    video = pitch.get("video_link")
    build = pitch.get("build_link")
    
    # 1. Hook quality (+0 to +3)
    hook_score = _evaluate_hook_quality(hook)
    score += hook_score * 0.3
    if hook_score < 3.0:
        reasons.append("Weak or generic hook")
    elif hook_score >= 7.0:
        reasons.append("Strong, specific hook")
    
    # 2. Описание quality (+0 to +2)
    desc_score = _evaluate_description_quality(pitch_text)
    score += desc_score
    if desc_score < 0.8:
        reasons.append("Description lacks clarity")
    
    # 3. Трейлер (+1.5)
    if video:
        score += 1.5
        reasons.append("Gameplay video present")
    else:
        reasons.append("Missing gameplay video")
    
    # 4. Demo readiness (+0 to +1.5)
    if build:
        score += 1.5
        reasons.append("Demo-ready")
    else:
        reasons.append("No playable demo yet")
    
    # 5. Жанровая читаемость (+0 to +1)
    if len(tags) >= 3:
        score += 1.0
    elif len(tags) < 1:
        reasons.append("Genre unclear")
    
    score = clamp(score, 0.0, 10.0)
    conf = "high"
    
    return score, conf, reasons


def _score_team_delivery(pitch: Dict[str, Any]) -> tuple[float, str, List[str]]:
    """C) Может ли команда доставить? (0-10)"""
    score = 5.0
    reasons = []
    conf = "low"  # По умолчанию в Discovery mode
    
    team_size = pitch.get("team_size", 1)
    released_before = pitch.get("released_before", False)
    timeline = pitch.get("timeline_months", 12)
    tags = pitch.get("tags", [])
    
    # 1. История релизов (+0 to +3)
    if released_before:
        score += 3.0
        conf = "high"
        reasons.append("Proven track record")
    else:
        reasons.append("First-time team")
    
    # 2. Размер команды vs scope
    genre_coeff = _get_content_heavy_coefficient(tags)
    if team_size <= 2 and genre_coeff >= 1.5:
        score -= 2.0
        reasons.append("Small team for content-heavy genre")
    elif team_size >= 3:
        score += 1.0
        conf = "medium"
        reasons.append("Team size adequate")
    
    # 3. Реалистичность timeline
    if timeline < 3 or timeline > 48:
        score -= 2.0
        reasons.append("Unrealistic timeline")
    elif 6 <= timeline <= 24:
        score += 1.0
    
    score = clamp(score, 0.0, 10.0)
    return score, conf, reasons


def _calculate_fixability(
    pitch: Dict[str, Any],
    pp: float,
    gtm: float,
    team: float,
    flags: List[Dict[str, Any]]
) -> tuple[float, Dict[str, float]]:
    """E) Насколько проблемы исправимы за 1-3 месяца?"""
    breakdown = {}
    total = 0.0
    
    hook = pitch.get("hook_one_liner", "")
    video = pitch.get("video_link")
    build = pitch.get("build_link")
    pitch_text = pitch.get("pitch_text", "")
    team_size = pitch.get("team_size", 1)
    tags = pitch.get("tags", [])
    
    # Слабый hook → +3
    if gtm < 6.0:
        hook_quality = _evaluate_hook_quality(hook)
        if hook_quality < 5.0:
            breakdown["weak_hook"] = 3.0
            total += 3.0
    
    # Нет трейлера → +2
    if not video:
        breakdown["no_video"] = 2.0
        total += 2.0
    
    # Нет демо → +2
    if not build:
        breakdown["no_demo"] = 2.0
        total += 2.0
    
    # Плохое описание → +2
    desc_quality = _evaluate_description_quality(pitch_text)
    if desc_quality < 1.0:
        breakdown["poor_description"] = 2.0
        total += 2.0
    
    # Мало тегов → +1
    if len(tags) < 3:
        breakdown["unclear_genre"] = 1.0
        total += 1.0
    
    # Штрафы за фундаментальные риски
    
    # Content-heavy + micro team → -4
    genre_coeff = _get_content_heavy_coefficient(tags)
    if team_size <= 2 and genre_coeff >= 1.5:
        breakdown["content_heavy_small_team"] = -4.0
        total -= 4.0
    
    # Фундаментальные продуктовые риски → -7
    if pp < 4.0:
        breakdown["fundamental_product_risk"] = -7.0
        total -= 7.0
    
    score = clamp(total, 0.0, 10.0)
    return score, breakdown


def _detect_flags(
    pitch: Dict[str, Any],
    pp: float,
    gtm: float,
    team: float
) -> List[Dict[str, Any]]:
    """Обнаружение риск-флагов"""
    flags = []
    
    video = pitch.get("video_link")
    build = pitch.get("build_link")
    team_size = pitch.get("team_size", 1)
    timeline = pitch.get("timeline_months", 12)
    tags = pitch.get("tags", [])
    
    # Content-heavy small team
    genre_coeff = _get_content_heavy_coefficient(tags)
    if team_size <= 2 and genre_coeff >= 1.5:
        flags.append({
            "code": "CONTENT_HEAVY_SMALL_TEAM",
            "severity": "high",
            "penalty": 3
        })
    
    # Unrealistic timeline
    if timeline < 3 or timeline > 48:
        flags.append({
            "code": "UNREALISTIC_TIMELINE",
            "severity": "high",
            "penalty": 3
        })
    
    # Fundamental product weakness
    if pp < 4.5:
        flags.append({
            "code": "FUNDAMENTAL_PRODUCT_WEAKNESS",
            "severity": "high",
            "penalty": 4
        })
    
    # Missing critical assets
    if not video:
        flags.append({
            "code": "NO_GAMEPLAY_VIDEO",
            "severity": "high",
            "penalty": 4
        })
    
    if not build:
        flags.append({
            "code": "NO_PLAYABLE_BUILD",
            "severity": "high",
            "penalty": 4
        })
    
    # Negative gap
    gap = pp - gtm
    if gap < -1.0:
        flags.append({
            "code": "OVERPROMISING",
            "severity": "medium",
            "penalty": 2
        })
    
    return flags


def _determine_investment_profile(
    pp: float,
    gtm: float,
    team: float,
    gap: float,
    fix: float,
    flags: List[Dict[str, Any]],
    team_conf: str
) -> str:
    """Определение инвестиционного профиля"""
    
    high_flags = [f for f in flags if f.get("code") in [
        "FUNDAMENTAL_PRODUCT_WEAKNESS",
        "UNREALISTIC_TIMELINE"
    ]]
    
    # NOT_INVESTABLE - проверяем первым делом критические проблемы
    if high_flags:
        return "NOT_INVESTABLE"
    if pp < 5.0 and fix < 5.0:
        return "NOT_INVESTABLE"
    
    # PRODUCT_RISK - слабый продукт или overpromising
    if pp < 6.0:
        return "PRODUCT_RISK"
    if gap < 0:  # Overpromising (маркетинг лучше чем продукт)
        return "PRODUCT_RISK"
    
    # TEAM_RISK - проблемы с командой
    if any(f.get("code") in ["CONTENT_HEAVY_SMALL_TEAM", "UNREALISTIC_TIMELINE"] for f in flags):
        return "TEAM_RISK"
    if team_conf != "low" and team <= 4.0:
        return "TEAM_RISK"
    
    # UNDERMARKETED_GEM - отличный продукт с большим gap
    if pp >= 7.0 and gap >= 2.0 and fix >= 7.0:
        return "UNDERMARKETED_GEM"
    
    # MARKETING_FIXABLE - хороший продукт с умеренным gap
    if pp >= 6.0 and gap >= 1.5 and fix >= 6.0:
        return "MARKETING_FIXABLE"
    
    # STRONG_BALANCED - оба показателя высокие, gap минимальный (0-1.5)
    # Это ХОРОШО - значит продукт и маркетинг на одном уровне
    if pp >= 7.0 and gtm >= 7.0 and 0 <= gap < 1.5:
        return "STRONG_BALANCED"
    
    # По умолчанию - умеренно хорошо, можно улучшить маркетинг
    return "MARKETING_FIXABLE"


def _identify_fixable_weaknesses(
    pitch: Dict[str, Any],
    gtm: float,
    fix_bd: Dict[str, float]
) -> List[str]:
    """Что конкретно сломано"""
    weaknesses = []
    
    for key, value in fix_bd.items():
        if value > 0:
            if key == "weak_hook":
                weaknesses.append("Hook is generic/unclear - needs emotional angle")
            elif key == "no_video":
                weaknesses.append("Missing gameplay video")
            elif key == "no_demo":
                weaknesses.append("No playable demo for testing")
            elif key == "poor_description":
                weaknesses.append("Pitch lacks structure/clarity")
            elif key == "unclear_genre":
                weaknesses.append("Genre positioning unclear")
    
    return weaknesses[:6]


def _generate_investor_actions(
    weaknesses: List[str],
    profile: str,
    pitch: Dict[str, Any]
) -> List[str]:
    """Что может сделать инвестор"""
    actions = []
    
    if "Hook" in str(weaknesses):
        actions.append("Workshop hook with team - find emotional core")
    
    if "Missing gameplay video" in str(weaknesses):
        actions.append("Fund 60-90sec gameplay trailer production")
    
    if "No playable demo" in str(weaknesses):
        actions.append("Prioritize demo slice for next festival")
    
    if "Pitch lacks" in str(weaknesses):
        actions.append("Rewrite pitch deck with experienced copywriter")
    
    if profile == "UNDERMARKETED_GEM":
        actions.append("Launch festival campaign immediately")
        actions.append("Allocate small paid UA budget for validation")
    
    if not actions:
        actions.append("Move to due diligence (budget/rights/team)")
    
    return actions[:6]


def _generate_decision_summary(
    profile: str,
    pp: float,
    gap: float,
    fix: float,
    flags: List[Dict[str, Any]]
) -> str:
    """Краткое объяснение решения"""
    
    if profile == "UNDERMARKETED_GEM":
        return f"Strong product (PP={pp:.1f}) with major marketing gap (GAP={gap:.1f}). High fixability (FIX={fix:.1f}). Prime investment opportunity."
    
    elif profile == "STRONG_BALANCED":
        return f"Excellent product and marketing execution (PP={pp:.1f}, GTM={pp-gap:.1f}). Well-balanced pitch ready for investment."
    
    elif profile == "MARKETING_FIXABLE":
        return f"Solid product (PP={pp:.1f}) with fixable marketing issues (GAP={gap:.1f}, FIX={fix:.1f}). Good upside potential."
    
    elif profile == "PRODUCT_RISK":
        return f"Product concerns (PP={pp:.1f}) or overpromising detected (GAP={gap:.1f}). Core gameplay needs validation."
    
    elif profile == "TEAM_RISK":
        flag_str = ", ".join(f.get("code", "") for f in flags[:2]) if flags else "weak team signals"
        return f"Delivery risk detected: {flag_str}. Consider team augmentation."
    
    else:
        return f"Fundamental issues (PP={pp:.1f}, FIX={fix:.1f}) or critical flags. Not suitable for investment."


def _compute_legacy_score(
    pp: float,
    gtm: float,
    team: float,
    flags: List[Dict[str, Any]]
) -> float:
    """Вычислить legacy score для обратной совместимости"""
    base = (pp * 0.35 + gtm * 0.35 + team * 0.30) * 10.0
    penalty = sum(f.get("penalty", 0) for f in flags) * 2
    return clamp(base - penalty, 0.0, 100.0)


def _verdict_from_score(score: float, flags: List[Dict[str, Any]]) -> str:
    """Legacy verdict"""
    if score >= 75 and not any(f.get("severity") == "high" for f in flags):
        return "PASS"
    if score >= 55:
        return "WATCH"
    return "NO"


# === Вспомогательные функции ===

def _evaluate_genre_viability(tags: List[str]) -> float:
    """Оценка коммерческой привлекательности жанра"""
    tags_lower = [t.lower() for t in tags]
    
    high_commercial = ["roguelike", "roguelite", "deckbuilder", "tower defense", "card game", "multiplayer", "co-op"]
    medium_commercial = ["puzzle", "platformer", "horror", "survival", "rpg"]
    niche = ["visual novel", "walking simulator", "art game", "experimental"]
    
    for tag in tags_lower:
        if any(hc in tag for hc in high_commercial):
            return 2.0
        if any(mc in tag for mc in medium_commercial):
            return 1.0
        if any(n in tag for n in niche):
            return 0.3
    
    return 1.0


def _get_content_heavy_coefficient(tags: List[str]) -> float:
    """Получить коэффициент content-heavy из жанра"""
    tags_lower = [t.lower() for t in tags]
    
    max_coeff = 1.0
    for tag in tags_lower:
        for genre, coeff in GENRE_COEFFICIENTS.items():
            if genre in tag:
                max_coeff = max(max_coeff, coeff)
    
    return max_coeff


def _evaluate_core_loop_clarity(desc: str, tags: List[str]) -> float:
    """Эвристическая оценка ясности core loop"""
    if not desc or len(desc) < 50:
        return 0.3
    
    desc_lower = desc.lower()
    
    gameplay_words = ["collect", "build", "fight", "explore", "craft", "manage", "defend", "attack", "upgrade", "unlock", "progress"]
    
    count = sum(1 for word in gameplay_words if word in desc_lower)
    
    if count >= 4:
        return 2.0
    elif count >= 2:
        return 1.5
    elif count >= 1:
        return 0.8
    else:
        return 0.3


def _evaluate_hook_quality(hook: str) -> float:
    """Эвристическая оценка hook"""
    if not hook or len(hook) < 10:
        return 0.5
    
    hook_lower = hook.lower()
    
    score = 2.0
    
    # Длина (не слишком длинная)
    if len(hook) <= 120:
        score += 2.0
    
    # Специфичность
    if any(k in hook_lower for k in ["meets", "vs", "x", "like"]):
        score += 1.5
    
    # Жанр упомянут
    if any(k in hook_lower for k in ["roguelike", "survival", "builder", "strategy", "rpg", "horror"]):
        score += 2.0
    
    # Уникальность
    if any(k in hook_lower for k in ["unique", "new", "procedural", "dynamic"]):
        score += 1.5
    
    # Штраф за generic
    if any(gp in hook_lower for gp in ["exciting", "epic", "amazing", "awesome"]):
        score -= 1.0
    
    return clamp(score, 0.0, 10.0)


def _evaluate_description_quality(desc: str) -> float:
    """Качество описания"""
    if not desc or len(desc) < 100:
        return 0.2
    
    score = 1.0
    
    if len(desc) >= 300:
        score += 0.5
    
    if "\n" in desc or "•" in desc or "- " in desc:
        score += 0.5
    
    return min(2.0, score)