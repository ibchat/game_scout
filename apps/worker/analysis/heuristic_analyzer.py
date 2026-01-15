"""
Heuristic Narrative Analyzer (NO API REQUIRED)
Эвристический анализатор без использования платного API
"""
import re
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class HeuristicNarrativeAnalyzer:
    """Анализатор на основе правил и эвристик"""
    
    # Ключевые слова для narrative levels
    BIOLOGICAL_KEYWORDS = [
        'survive', 'survival', 'hunger', 'death', 'kill', 'threat', 'danger',
        'horror', 'zombie', 'apocalypse', 'escape', 'hide', 'fear'
    ]
    
    SOCIAL_KEYWORDS = [
        'relationship', 'friend', 'romance', 'community', 'team', 'party',
        'multiplayer', 'social', 'diplomacy', 'negotiate', 'alliance'
    ]
    
    IDENTITY_KEYWORDS = [
        'destiny', 'purpose', 'journey', 'discover', 'transform', 'hero',
        'legend', 'chosen', 'legacy', 'meaning', 'path', 'calling'
    ]
    
    META_KEYWORDS = [
        'meta', 'game', 'player', 'fourth wall', 'aware', 'reality',
        'simulation', 'glitch', 'developer', 'breaking'
    ]
    
    # Ключевые слова для dramatic patterns
    THREAT_SAFETY_KEYWORDS = ['survive', 'escape', 'safe', 'shelter', 'protect', 'defense']
    WEAK_STRONG_KEYWORDS = ['level up', 'upgrade', 'power', 'progression', 'stronger', 'grow']
    CHAOS_ORDER_KEYWORDS = ['build', 'manage', 'organize', 'strategy', 'control', 'empire']
    LOSS_COMPENSATION_KEYWORDS = ['restore', 'rebuild', 'revenge', 'reclaim', 'lost', 'return']
    FORBIDDEN_VIOLATION_KEYWORDS = ['freedom', 'break', 'rebel', 'escape', 'defy', 'revolution']
    HUMILIATION_REVENGE_KEYWORDS = ['revenge', 'payback', 'justice', 'vengeance', 'betray']
    MYSTERY_REVELATION_KEYWORDS = ['mystery', 'discover', 'investigate', 'solve', 'puzzle', 'detective']
    
    def analyze_game(self, game_data: Dict) -> Dict:
        """Полный эвристический анализ игры"""
        
        text = self._prepare_text(game_data)
        
        # Step 1: Classify narrative levels
        narrative_level = self._classify_narrative_level(text)
        
        # Step 2: Classify dramatic patterns
        dramatic_pattern = self._classify_dramatic_pattern(text)
        
        # Step 3: Score Product Potential (эвристика)
        pp_score = self._score_product_potential(
            narrative_level, dramatic_pattern, game_data
        )
        
        # Step 4: Score GTM Execution (эвристика)
        gtm_score = self._score_gtm_execution(game_data, text)
        
        # Step 5: Calculate GAP
        gap_score = pp_score - gtm_score
        gap_category = "strong" if gap_score >= 3 else "medium" if gap_score >= 2 else "weak"
        
        # Step 6: Fixability (эвристика)
        fixability = self._analyze_fixability(game_data, pp_score, gtm_score)
        
        # Step 7: Investor category
        investor_category = self._determine_category(
            pp_score, gap_score, fixability['fixability_score']
        )
        
        return {
            "narrative_level": narrative_level,
            "dramatic_pattern": dramatic_pattern,
            "product_potential": pp_score,
            "pp_details": self._get_pp_breakdown(narrative_level, dramatic_pattern),
            "gtm_execution": gtm_score,
            "gtm_details": self._get_gtm_breakdown(game_data, text),
            "gap_score": gap_score,
            "gap_category": gap_category,
            "fixability": fixability,
            "investor_category": investor_category,
            "analysis_method": "heuristic",
            "confidence": "medium"  # Эвристика менее точна чем LLM
        }
    
    def _prepare_text(self, game_data: Dict) -> str:
        """Подготовка текста для анализа"""
        parts = [
            game_data.get('title', ''),
            game_data.get('description', ''),
            game_data.get('short_description', ''),
            ' '.join(game_data.get('tags', []))
        ]
        return ' '.join(parts).lower()
    
    def _classify_narrative_level(self, text: str) -> Dict:
        """Классификация уровня нарратива"""
        scores = {
            'biological': self._count_keywords(text, self.BIOLOGICAL_KEYWORDS),
            'social': self._count_keywords(text, self.SOCIAL_KEYWORDS),
            'identity': self._count_keywords(text, self.IDENTITY_KEYWORDS),
            'meta': self._count_keywords(text, self.META_KEYWORDS)
        }
        
        # Сортируем по количеству совпадений
        sorted_levels = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        primary = sorted_levels[0][0] if sorted_levels[0][1] > 0 else None
        secondary = sorted_levels[1][0] if len(sorted_levels) > 1 and sorted_levels[1][1] > 2 else None
        
        confidence = min(sorted_levels[0][1] / 10, 1.0) if primary else 0.0
        blurred_focus = len([s for s in sorted_levels if s[1] > 3]) > 2
        
        return {
            "primary_level": primary,
            "secondary_level": secondary,
            "confidence": round(confidence, 2),
            "blurred_focus": blurred_focus,
            "evidence": f"Found {sorted_levels[0][1]} keyword matches for {primary}"
        }
    
    def _classify_dramatic_pattern(self, text: str) -> Dict:
        """Классификация драматургического паттерна"""
        patterns = {
            'threat_to_safety': self._count_keywords(text, self.THREAT_SAFETY_KEYWORDS),
            'weak_to_strong': self._count_keywords(text, self.WEAK_STRONG_KEYWORDS),
            'chaos_to_order': self._count_keywords(text, self.CHAOS_ORDER_KEYWORDS),
            'loss_to_compensation': self._count_keywords(text, self.LOSS_COMPENSATION_KEYWORDS),
            'forbidden_to_violation': self._count_keywords(text, self.FORBIDDEN_VIOLATION_KEYWORDS),
            'humiliation_to_revenge': self._count_keywords(text, self.HUMILIATION_REVENGE_KEYWORDS),
            'mystery_to_revelation': self._count_keywords(text, self.MYSTERY_REVELATION_KEYWORDS)
        }
        
        sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
        
        primary = sorted_patterns[0][0] if sorted_patterns[0][1] > 0 else None
        secondary = sorted_patterns[1][0] if len(sorted_patterns) > 1 and sorted_patterns[1][1] > 2 else None
        
        confidence = min(sorted_patterns[0][1] / 8, 1.0) if primary else 0.0
        
        # Определяем pattern_in_gameplay (упрощенно)
        pattern_in_gameplay = "true" if sorted_patterns[0][1] > 5 else "weak" if sorted_patterns[0][1] > 2 else "false"
        
        return {
            "primary_pattern": primary,
            "secondary_pattern": secondary,
            "confidence": round(confidence, 2),
            "pattern_in_gameplay": pattern_in_gameplay,
            "marketing_fiction": pattern_in_gameplay == "false",
            "player_state_before": self._infer_state_before(primary),
            "player_state_after": self._infer_state_after(primary),
            "evidence": f"Found {sorted_patterns[0][1]} pattern indicators"
        }
    
    def _score_product_potential(self, narrative_level: Dict, dramatic_pattern: Dict, game_data: Dict) -> float:
        """Scoring Product Potential (0-10)"""
        
        # Pattern strength (базовые паттерны сильнее)
        strong_patterns = ['threat_to_safety', 'weak_to_strong', 'chaos_to_order']
        pattern_strength = 8 if dramatic_pattern['primary_pattern'] in strong_patterns else 6
        
        # Universality (biological и social универсальнее)
        universal_levels = ['biological', 'social']
        universality = 9 if narrative_level['primary_level'] in universal_levels else 6
        
        # Genre fit (пока упрощенно - 7)
        genre_fit = 7
        
        # Loop repeatability (если паттерн в геймплее)
        loop_repeatability = 9 if dramatic_pattern['pattern_in_gameplay'] == "true" else 5
        
        # Средний PP
        pp = (pattern_strength + universality + genre_fit + loop_repeatability) / 4
        
        return round(pp, 1)
    
    def _score_gtm_execution(self, game_data: Dict, text: str) -> float:
        """Scoring GTM Execution (0-10) с учётом реальных метрик"""
        
        # НОВОЕ: Учитываем реальные метрики из базы
        reviews_total = game_data.get('reviews_total', 0)
        positive_reviews = game_data.get('positive_reviews', 0)
        owners_min = game_data.get('owners_min', 0)
        rating = game_data.get('rating', 0)
        
        # Если игра супер-популярная (>100k отзывов или >10M владельцев)
        # значит маркетинг РАБОТАЕТ отлично!
        if (reviews_total and reviews_total > 100000) or (owners_min and owners_min > 10000000):
            return 9.5  # Отличный маркетинг у популярных игр
        
        # Если игра популярная (>10k отзывов или >1M владельцев)
        if (reviews_total and reviews_total > 10000) or (owners_min and owners_min > 1000000):
            return 8.5  # Хороший маркетинг
        
        # Если игра известная (>1k отзывов или >100k владельцев)
        if (reviews_total and reviews_total > 1000) or (owners_min and owners_min > 100000):
            return 7.5  # Нормальный маркетинг
        
        # Для менее известных игр - смотрим на описание
        short_desc = game_data.get('short_description', '')[:200].lower()
        hook_has_pattern = any(kw in short_desc for kw in self.WEAK_STRONG_KEYWORDS + self.THREAT_SAFETY_KEYWORDS)
        hook_clarity = 8 if hook_has_pattern else 4
        
        # Trailer alignment
        trailer_score = 7 if game_data.get('has_trailer') else 3
        
        # Demo intro
        demo_score = 7 if game_data.get('has_demo') else 5
        
        # Page clarity
        desc_len = len(game_data.get('description', ''))
        screenshots = game_data.get('screenshots_count', 0)
        page_clarity = min(10, (desc_len / 500 * 5) + (screenshots / 5 * 5))
        
        gtm = (hook_clarity + trailer_score + demo_score + page_clarity) / 4
        
        return round(gtm, 1)
    
    def _analyze_fixability(self, game_data: Dict, pp: float, gtm: float) -> Dict:
        """Анализ исправимости"""
        
        # Простая логика: если GTM низкий но PP высокий - все исправимо
        gap = pp - gtm
        
        fixable_trailer = gap > 1 and not game_data.get('has_trailer')
        fixable_hook = gap > 1
        fixable_demo = gap > 1.5 and not game_data.get('has_demo')
        
        main_issues = []
        if fixable_trailer:
            main_issues.append("No trailer or trailer doesn't express pattern")
        if fixable_hook:
            main_issues.append("Hook text doesn't clearly communicate transformation")
        if fixable_demo:
            main_issues.append("Demo missing or doesn't showcase core pattern")
        
        recommended_actions = []
        if fixable_hook:
            recommended_actions.append("Rewrite hook - first sentence must show pattern")
        if fixable_trailer:
            recommended_actions.append("Create/recut trailer - first 10 sec shows pattern")
        if fixable_demo:
            recommended_actions.append("Add demo that delivers pattern within 5 minutes")
        
        fixability_score = 8 if gap > 2 else 6 if gap > 1 else 3
        
        return {
            "fixable_trailer": fixable_trailer,
            "fixable_hook": fixable_hook,
            "fixable_demo": fixable_demo,
            "fixable_page_layout": gap > 1,
            "not_fixable_gameplay": False,  # Эвристика не может определить
            "main_issues": main_issues,
            "recommended_actions": recommended_actions,
            "why_matters": f"High PP ({pp}) but weak GTM ({gtm}). Pattern is strong but hidden.",
            "estimated_fix_days": 30 if gap > 2 else 45,
            "fixability_score": fixability_score
        }
    
    def _determine_category(self, pp: float, gap: float, fix: float) -> str:
        """Определение инвесторской категории"""
        if pp >= 7 and gap >= 2 and fix >= 7:
            return "undermarketed_gem"
        elif pp >= 6 and gap >= 1.5 and fix >= 6:
            return "marketing_fixable"
        elif pp < 5 or fix < 4:
            return "not_investable"
        else:
            return "product_risk"
    
    def _count_keywords(self, text: str, keywords: List[str]) -> int:
        """Подсчет ключевых слов в тексте"""
        count = 0
        for keyword in keywords:
            count += len(re.findall(r'\b' + re.escape(keyword) + r'\b', text))
        return count
    
    def _infer_state_before(self, pattern: Optional[str]) -> str:
        """Вывод состояния игрока ДО"""
        states = {
            'threat_to_safety': 'Vulnerable, exposed to danger',
            'weak_to_strong': 'Powerless, lacking capability',
            'chaos_to_order': 'Overwhelmed by disorder',
            'loss_to_compensation': 'Missing something important',
            'forbidden_to_violation': 'Constrained, limited',
            'humiliation_to_revenge': 'Dishonored, wronged',
            'mystery_to_revelation': 'Confused, lacking knowledge'
        }
        return states.get(pattern, 'Unknown state')
    
    def _infer_state_after(self, pattern: Optional[str]) -> str:
        """Вывод состояния игрока ПОСЛЕ"""
        states = {
            'threat_to_safety': 'Safe, secured',
            'weak_to_strong': 'Powerful, capable',
            'chaos_to_order': 'In control, organized',
            'loss_to_compensation': 'Restored, fulfilled',
            'forbidden_to_violation': 'Free, unrestricted',
            'humiliation_to_revenge': 'Vindicated, avenged',
            'mystery_to_revelation': 'Enlightened, knowledgeable'
        }
        return states.get(pattern, 'Transformed state')
    
    def _get_pp_breakdown(self, narrative: Dict, pattern: Dict) -> Dict:
        """Детализация PP"""
        return {
            "pattern_strength": 7,
            "universality": 8,
            "genre_fit": 7,
            "loop_repeatability": 7
        }
    
    def _get_gtm_breakdown(self, game_data: Dict, text: str) -> Dict:
        """Детализация GTM"""
        return {
            "hook_clarity": 6,
            "trailer_alignment": 5,
            "demo_intro": 5,
            "page_clarity": 6
        }


# Global instance
heuristic_analyzer = HeuristicNarrativeAnalyzer()
