"""
Trends Brain - Investment Intelligence Engine
Нормализует сигналы, интерпретирует поведение рынка, объясняет решения.

Это "мозг" платформы, который превращает сырые данные в объяснимый инвестиционный интеллект.
"""
import logging
import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import statistics

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class SignalStrength:
    """Нормализованная сила сигнала [0..1]"""
    value: float
    percentile: Optional[float] = None  # Процентиль в выборке
    z_score: Optional[float] = None  # Z-score относительно выборки
    explanation: str = ""


@dataclass
class GameFlags:
    """Логические флаги для игры"""
    has_real_growth: bool
    is_evergreen_giant: bool
    is_hype_spike: bool
    is_low_quality_growth: bool
    is_new_release: bool
    is_rediscovered_old_game: bool
    
    # Причины для каждого флага
    reasons: Dict[str, str]


@dataclass
class ScoreComponents:
    """Компоненты emerging score (Engine v4: confirmation/momentum/catalyst, v5: контекстное влияние)"""
    # Legacy components (сохраняем для обратной совместимости)
    growth_component: float = 0.0
    velocity_component: float = 0.0
    sentiment_component: float = 0.0
    novelty_component: float = 0.0
    penalty_component: float = 0.0
    
    # Engine v4: новая компонентная схема
    score_confirmation: float = 0.0  # 0..50: Steam reviews/store как подтверждение
    score_momentum: float = 0.0  # 0..30: Social signals (Reddit/YouTube/Twitch) как импульс
    score_catalyst: float = 0.0  # 0..20: News/updates как катализатор
    
    # Engine v5: отдельные компоненты для контекстного влияния
    reddit_component: float = 0.0  # Может быть отрицательным (anti-hype)
    youtube_component: float = 0.0  # Может быть отрицательным (anti-hype)
    
    def total(self) -> float:
        """Итоговый score: сумма новых компонентов (или legacy если новые = 0)"""
        # Если новые компоненты заполнены - используем их
        if self.score_confirmation > 0 or self.score_momentum > 0 or self.score_catalyst > 0:
            # v5: включаем отдельные reddit/youtube компоненты (могут быть отрицательными)
            social_adjustment = self.reddit_component + self.youtube_component
            return max(0.0, self.score_confirmation + self.score_momentum + self.score_catalyst + social_adjustment - self.penalty_component)
        # Иначе legacy формула
        return (
            self.growth_component +
            self.velocity_component +
            self.sentiment_component +
            self.novelty_component -
            self.penalty_component
        )


@dataclass
class EmergingAnalysis:
    """Полный анализ игры для emerging (v3: с confidence и stage, v5: lifecycle + anti-hype)"""
    steam_app_id: int
    name: Optional[str]
    emerging_score: float
    verdict: str  # "Сильный органический рост", "Хайп-всплеск", "Низкокачественный рост", etc.
    explanation: List[str]
    flags: GameFlags
    score_components: ScoreComponents
    signal_strengths: Dict[str, SignalStrength]
    
    # Brain v3 fields
    confidence_score: float = 0.0  # 0..100
    confidence_level: str = "LOW"  # LOW/MEDIUM/HIGH
    stage: str = "NOISE"  # EARLY/CONFIRMING/BREAKOUT/FADING/NOISE
    why_now: str = ""
    signals_used: List[str] = None  # List of sources: ["steam_reviews", "reddit", "youtube"]
    
    # Engine v4: evidence links
    evidence: List[Dict[str, Any]] = None  # List of evidence events with url, title, source
    
    # Lifecycle Intelligence v5: жизненный цикл игры
    lifecycle_stage: str = "MATURITY"  # PRE_RELEASE/SOFT_LAUNCH/BREAKOUT/GROWTH/MATURITY/DECLINE/RELAUNCH_CANDIDATE
    
    # Anti-Hype Layer v5: тип роста
    growth_type: str = "ORGANIC"  # ORGANIC/HYPE/NEWS_DRIVEN/PLATFORM_DRIVEN/MIXED
    
    # WHY NOW v2: структурированное объяснение
    why_now_v2: Dict[str, Any] = None  # Структурированный объект с основным_триггером, факторами, аномалией, рисками
    
    # Confidence как фактор ранжирования
    final_rank_score: float = 0.0
    
    # Engine v5: Debug trace (только при debug=True)
    debug_trace: Optional[Dict[str, Any]] = None  # emerging_score * (confidence_score / 100)
    
    def __post_init__(self):
        if self.signals_used is None:
            self.signals_used = []
        if self.evidence is None:
            self.evidence = []
        if self.why_now_v2 is None:
            self.why_now_v2 = {
                "основной_триггер": "",
                "дополнительные_факторы": [],
                "аномалия": "",
                "риски": "",
                "инвестиционное_окно_дней": 0
            }


class TrendsBrain:
    """
    Мозг платформы Game Scout - интерпретирующая система принятия решений.
    
    Принципы:
    - Вся бизнес-логика ТОЛЬКО здесь
    - Сигналы интерпретируются, а не просто суммируются
    - Контекст игры влияет на интерпретацию
    - Объяснимость: каждое решение можно объяснить
    """
    
    # Константы для скоринга (не magic numbers)
    SCORE_WEIGHT_CONFIRMATION = 0.5  # Steam подтверждение
    SCORE_WEIGHT_MOMENTUM = 0.3      # Social импульс
    SCORE_WEIGHT_CATALYST = 0.2      # News/Events катализатор
    
    # Пороги для интерпретации
    STEAM_DELTA_7D_THRESHOLD_WEAK = 10
    STEAM_DELTA_7D_THRESHOLD_MEDIUM = 50
    STEAM_DELTA_7D_THRESHOLD_STRONG = 150
    
    REDDIT_POSTS_THRESHOLD_MIN = 3  # Минимум для учёта
    REDDIT_VELOCITY_THRESHOLD = 1   # Минимум velocity для валидности
    
    YOUTUBE_VIDEOS_THRESHOLD_MIN = 2  # Минимум для учёта
    YOUTUBE_VELOCITY_THRESHOLD = 1     # Минимум velocity для валидности
    
    def __init__(self, db: Session):
        self.db = db
        self.today = date.today()
        self._distribution_cache: Optional[Dict[str, List[float]]] = None
        
        # Импортируем функции интерпретации (Engine v5)
        from apps.worker.analysis.trends_brain_v5_interpretation import (
            interpret_steam,
            interpret_reddit,
            interpret_youtube,
            interpret_news
        )
        self.interpret_steam = interpret_steam
        self.interpret_reddit = interpret_reddit
        self.interpret_youtube = interpret_youtube
        self.interpret_news = interpret_news
    
    def _get_distribution(self, signal_type: str) -> List[float]:
        """Получить распределение значений сигнала для нормализации"""
        if self._distribution_cache is None:
            self._distribution_cache = {}
        
        if signal_type in self._distribution_cache:
            return self._distribution_cache[signal_type]
        
        # Получаем распределение из trends_game_daily за последние 30 дней
        query = text("""
            SELECT DISTINCT
                reviews_delta_7d,
                reviews_delta_1d,
                positive_ratio
            FROM trends_game_daily
            WHERE day >= :start_date
              AND day <= :end_date
              AND reviews_delta_7d IS NOT NULL
        """)
        
        rows = self.db.execute(
            query,
            {
                "start_date": self.today - timedelta(days=30),
                "end_date": self.today
            }
        ).mappings().all()
        
        delta_7d_values = [float(r["reviews_delta_7d"]) for r in rows if r["reviews_delta_7d"] is not None]
        delta_1d_values = [float(r["reviews_delta_1d"]) for r in rows if r["reviews_delta_1d"] is not None]
        positive_ratio_values = [float(r["positive_ratio"]) for r in rows if r["positive_ratio"] is not None]
        
        self._distribution_cache["reviews_delta_7d"] = delta_7d_values
        self._distribution_cache["reviews_delta_1d"] = delta_1d_values
        self._distribution_cache["positive_ratio"] = positive_ratio_values
        
        return self._distribution_cache.get(signal_type, [])
    
    def normalize_signal(
        self,
        signal_type: str,
        value: Optional[float],
        use_percentile: bool = True
    ) -> SignalStrength:
        """
        Нормализует сигнал в [0..1] на основе распределения.
        
        Args:
            signal_type: 'reviews_delta_7d', 'reviews_delta_1d', 'positive_ratio'
            value: сырое значение сигнала
            use_percentile: использовать процентиль (True) или z-score (False)
        """
        if value is None:
            return SignalStrength(
                value=0.0,
                explanation="Нет данных"
            )
        
        distribution = self._get_distribution(signal_type)
        
        if not distribution:
            # Если нет данных для нормализации, используем простую эвристику
            if signal_type == "reviews_delta_7d":
                normalized = min(1.0, max(0.0, value / 500.0))
                return SignalStrength(
                    value=normalized,
                    explanation=f"Рост {value:.0f} отзывов за 7 дней (эвристика)"
                )
            elif signal_type == "reviews_delta_1d":
                normalized = min(1.0, max(0.0, value / 100.0))
                return SignalStrength(
                    value=normalized,
                    explanation=f"Рост {value:.0f} отзывов за 1 день (эвристика)"
                )
            elif signal_type == "positive_ratio":
                # Для positive_ratio: 0.7 = 0, 0.95 = 1
                normalized = min(1.0, max(0.0, (value - 0.7) / 0.25))
                return SignalStrength(
                    value=normalized,
                    explanation=f"Положительных отзывов {value*100:.1f}% (эвристика)"
                )
            else:
                return SignalStrength(value=0.0, explanation="Неизвестный тип сигнала")
        
        # Вычисляем процентиль
        sorted_dist = sorted(distribution)
        if not sorted_dist:
            return SignalStrength(value=0.0, explanation="Нет данных для сравнения")
        
        percentile = sum(1 for x in sorted_dist if x <= value) / len(sorted_dist)
        
        # Вычисляем z-score
        mean = statistics.mean(sorted_dist)
        if len(sorted_dist) > 1:
            stdev = statistics.stdev(sorted_dist)
            z_score = (value - mean) / stdev if stdev > 0 else 0.0
        else:
            z_score = 0.0
        
        # Нормализуем в [0..1]
        if use_percentile:
            normalized = percentile
        else:
            # Z-score -> [0..1]: используем sigmoid-like функцию
            # z=0 -> 0.5, z=2 -> ~0.88, z=-2 -> ~0.12
            normalized = 1.0 / (1.0 + 2.718 ** (-z_score))
        
        # Для positive_ratio: инвертируем логику (высокий ratio = хорошо)
        if signal_type == "positive_ratio":
            normalized = percentile  # Уже в правильном порядке
        
        explanation = f"{signal_type}: {value:.1f} (percentile: {percentile*100:.1f}%, z-score: {z_score:.2f})"
        
        return SignalStrength(
            value=normalized,
            percentile=percentile,
            z_score=z_score,
            explanation=explanation
        )
    
    def compute_flags(
        self,
        steam_app_id: int,
        release_date: Optional[date],
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int],
        reviews_delta_1d: Optional[int],
        positive_ratio: Optional[float],
        days_since_release: Optional[int] = None
    ) -> GameFlags:
        """
        Вычисляет логические флаги для игры.
        """
        reasons: Dict[str, str] = {}
        
        # Вычисляем возраст игры
        if release_date:
            days_since_release = (self.today - release_date).days
            years_since_release = days_since_release / 365.0
        else:
            years_since_release = None
        
        # 1. is_evergreen_giant
        # Логическое исключение: старые игры с большим количеством отзывов без реального роста
        # НЕ по ID, а по характеристикам (возраст + отзывы + отсутствие устойчивого всплеска)
        is_evergreen_giant = False
        if years_since_release and years_since_release > 3:
            if reviews_total and reviews_total >= 10000:
                # Проверяем, есть ли реальный всплеск (не единичный день, а устойчивый рост)
                has_spike = False
                if reviews_delta_7d is not None and reviews_delta_7d >= 500:
                    # Дополнительная проверка: если 1д рост составляет >70% от 7д - это единичный всплеск, не рост
                    if reviews_delta_1d is None or reviews_delta_1d < reviews_delta_7d * 0.7:
                        has_spike = True
                
                if not has_spike:
                    is_evergreen_giant = True
                    reasons["is_evergreen_giant"] = f"Возраст {years_since_release:.1f} лет, {reviews_total} отзывов, нет устойчивого всплеска"
        
        # 2. is_new_release
        is_new_release = False
        if days_since_release is not None and days_since_release <= 90:
            is_new_release = True
            reasons["is_new_release"] = f"Выпущена {days_since_release} дней назад"
        
        # 3. is_rediscovered_old_game
        is_rediscovered_old_game = False
        if years_since_release and years_since_release > 2:
            if reviews_delta_7d and reviews_delta_7d > 100:
                if reviews_total and reviews_total < 5000:  # Не гигант
                    is_rediscovered_old_game = True
                    reasons["is_rediscovered_old_game"] = f"Старая игра ({years_since_release:.1f} лет) с ростом {reviews_delta_7d}"
        
        # 4. has_real_growth
        has_real_growth = False
        if reviews_delta_7d and reviews_delta_7d > 0:
            # Рост должен быть устойчивым (не только 1 день)
            if reviews_delta_1d and reviews_delta_1d > 0:
                # Проверяем, что рост не единичный всплеск
                if reviews_delta_7d >= reviews_delta_1d * 2:  # Рост распределён
                    has_real_growth = True
                    reasons["has_real_growth"] = f"Устойчивый рост: +{reviews_delta_7d} за 7д, +{reviews_delta_1d} за 1д"
            elif reviews_delta_7d >= 50:  # Даже без 1д данных, если 7д рост значительный
                has_real_growth = True
                reasons["has_real_growth"] = f"Рост +{reviews_delta_7d} за 7 дней"
        
        # 5. is_hype_spike
        is_hype_spike = False
        if reviews_delta_1d and reviews_delta_7d:
            # Если 1д рост составляет >50% от 7д роста - это всплеск
            if reviews_delta_1d > reviews_delta_7d * 0.5:
                is_hype_spike = True
                reasons["is_hype_spike"] = f"Всплеск: +{reviews_delta_1d} за 1д из {reviews_delta_7d} за 7д"
        
        # 6. is_low_quality_growth
        is_low_quality_growth = False
        if positive_ratio is not None and positive_ratio < 0.7:
            if reviews_delta_7d and reviews_delta_7d > 0:
                is_low_quality_growth = True
                reasons["is_low_quality_growth"] = f"Рост при низком рейтинге: {positive_ratio*100:.1f}% положительных"
        
        return GameFlags(
            has_real_growth=has_real_growth,
            is_evergreen_giant=is_evergreen_giant,
            is_hype_spike=is_hype_spike,
            is_low_quality_growth=is_low_quality_growth,
            is_new_release=is_new_release,
            is_rediscovered_old_game=is_rediscovered_old_game,
            reasons=reasons
        )
    
    def compute_score_components(
        self,
        signal_strengths: Dict[str, SignalStrength],
        flags: GameFlags,
        release_date: Optional[date],
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int] = None,
        # Engine v4: дополнительные сигналы
        reddit_posts_count_7d: Optional[int] = None,
        reddit_comments_count_7d: Optional[int] = None,
        reddit_velocity: Optional[int] = None,
        reddit_uniqueness: Optional[int] = None,
        youtube_videos_count_7d: Optional[int] = None,
        youtube_views_7d: Optional[int] = None,
        youtube_velocity: Optional[int] = None,
        youtube_channel_quality: Optional[float] = None,
        steam_news_posts_7d: Optional[int] = None,
        steam_news_velocity: Optional[int] = None,
        # Engine v5: lifecycle для контекстного влияния
        lifecycle_stage: Optional[str] = None
    ) -> ScoreComponents:
        """
        Вычисляет компоненты emerging score (Engine v5: контекстное влияние + anti-hype).
        """
        components = ScoreComponents()
        
        # Legacy components (для обратной совместимости)
        delta_7d_strength = signal_strengths.get("reviews_delta_7d", SignalStrength(0.0))
        components.growth_component = delta_7d_strength.value * 40
        
        delta_1d_strength = signal_strengths.get("reviews_delta_1d", SignalStrength(0.0))
        components.velocity_component = delta_1d_strength.value * 20
        
        pos_ratio_strength = signal_strengths.get("positive_ratio", SignalStrength(0.0))
        components.sentiment_component = pos_ratio_strength.value * 20
        
        if flags.is_new_release:
            components.novelty_component = 5.0
        elif flags.is_rediscovered_old_game:
            components.novelty_component = 3.0
        
        # Penalty
        if flags.is_evergreen_giant:
            components.penalty_component = 100.0
        elif flags.is_hype_spike:
            components.penalty_component = 15.0
        elif flags.is_low_quality_growth:
            components.penalty_component = 10.0
        
        # ===== Engine v4: Новая компонентная схема =====
        
        # 1. score_confirmation (0..50): Steam reviews/store как подтверждение
        confirmation_base = 0.0
        
        if delta_7d_strength.value > 0:
            confirmation_base += delta_7d_strength.value * 30
        
        if pos_ratio_strength.value > 0:
            confirmation_base += pos_ratio_strength.value * 15
        
        if reviews_total and reviews_total >= 100:
            scale_bonus = min(5.0, (reviews_total / 1000.0) * 5.0)
            confirmation_base += scale_bonus
        
        components.score_confirmation = min(50.0, confirmation_base)
        
        # 2. score_momentum (0..30): Social signals как импульс (базовая часть)
        # Детальная логика в reddit_component и youtube_component
        momentum_base = 0.0
        components.score_momentum = min(30.0, momentum_base)  # Будет пересчитан ниже
        
        # 3. score_catalyst (0..20): News/updates как катализатор
        catalyst_base = 0.0
        
        if steam_news_posts_7d and steam_news_posts_7d > 0:
            catalyst_base = min(20.0, steam_news_posts_7d * 10.0)
        
        if steam_news_velocity and steam_news_velocity > 0:
            catalyst_base += min(5.0, steam_news_velocity * 2.0)
        
        components.score_catalyst = min(20.0, catalyst_base)
        
        # ===== Engine v5: Контекстное влияние Reddit/YouTube =====
        
        # Определяем контекст влияния на основе lifecycle_stage
        has_steam_confirmation = components.score_confirmation > 10.0 or (reviews_delta_7d and reviews_delta_7d > 0)
        
        # Reddit component (контекстное влияние)
        reddit_component = 0.0
        
        if reddit_posts_count_7d and reddit_posts_count_7d > 0:
            # Базовый вес зависит от lifecycle
            if lifecycle_stage in ["PRE_RELEASE", "SOFT_LAUNCH", "EARLY"]:
                # Early stage: Reddit важен (ранний сигнал)
                reddit_base = min(12.0, (reddit_posts_count_7d / 10.0) * 12.0)
                if reddit_comments_count_7d and reddit_comments_count_7d > 0:
                    reddit_base += min(3.0, (reddit_comments_count_7d / 50.0) * 3.0)
                if reddit_uniqueness and reddit_uniqueness > 1:
                    reddit_base += min(2.0, reddit_uniqueness * 0.5)
                reddit_component = reddit_base
            elif lifecycle_stage in ["BREAKOUT", "GROWTH"]:
                # Growth stage: Reddit усиливает, но нужен Steam
                if has_steam_confirmation:
                    reddit_base = min(8.0, (reddit_posts_count_7d / 15.0) * 8.0)
                    if reddit_velocity and reddit_velocity > 0:
                        reddit_base += min(2.0, reddit_velocity * 0.3)
                    reddit_component = reddit_base
                else:
                    # Anti-hype: соц. шум без Steam = отрицательный компонент
                    reddit_component = -min(5.0, reddit_posts_count_7d * 0.5)
            elif lifecycle_stage in ["MATURITY", "DECLINE"]:
                # Mature stage: Reddit менее важен
                if has_steam_confirmation:
                    reddit_component = min(3.0, reddit_posts_count_7d * 0.2)
                else:
                    reddit_component = -min(3.0, reddit_posts_count_7d * 0.3)
            elif lifecycle_stage == "RELAUNCH_CANDIDATE":
                # Relaunch: Reddit важен как индикатор интереса
                reddit_base = min(10.0, (reddit_posts_count_7d / 8.0) * 10.0)
                if reddit_velocity and reddit_velocity > 0:
                    reddit_base += min(3.0, reddit_velocity * 0.5)
                reddit_component = reddit_base
            else:
                # По умолчанию: умеренное влияние
                if has_steam_confirmation:
                    reddit_component = min(5.0, reddit_posts_count_7d * 0.5)
                else:
                    reddit_component = -min(3.0, reddit_posts_count_7d * 0.3)
        
        components.reddit_component = reddit_component
        
        # YouTube component (контекстное влияние)
        youtube_component = 0.0
        
        if youtube_videos_count_7d and youtube_videos_count_7d > 0:
            # Базовый вес зависит от lifecycle
            if lifecycle_stage in ["BREAKOUT", "GROWTH"]:
                # Growth stage: YouTube важен (визуальный импульс)
                youtube_base = min(12.0, (youtube_videos_count_7d / 5.0) * 12.0)
                if youtube_views_7d and youtube_views_7d > 1000:
                    youtube_base += min(3.0, (youtube_views_7d / 10000.0) * 3.0)
                if youtube_channel_quality and youtube_channel_quality > 3.0:
                    youtube_base += min(2.0, youtube_channel_quality * 0.5)
                if has_steam_confirmation:
                    youtube_component = youtube_base
                else:
                    # Anti-hype: YouTube без Steam = отрицательный
                    youtube_component = -min(5.0, youtube_videos_count_7d * 0.5)
            elif lifecycle_stage in ["PRE_RELEASE", "SOFT_LAUNCH"]:
                # Early stage: YouTube как ранний индикатор
                youtube_base = min(8.0, (youtube_videos_count_7d / 3.0) * 8.0)
                if youtube_velocity and youtube_velocity > 0:
                    youtube_base += min(2.0, youtube_velocity * 0.4)
                youtube_component = youtube_base
            elif lifecycle_stage in ["MATURITY", "DECLINE"]:
                # Mature stage: YouTube менее важен
                if has_steam_confirmation:
                    youtube_component = min(3.0, youtube_videos_count_7d * 0.3)
                else:
                    youtube_component = -min(3.0, youtube_videos_count_7d * 0.3)
            elif lifecycle_stage == "RELAUNCH_CANDIDATE":
                # Relaunch: YouTube важен
                youtube_base = min(10.0, (youtube_videos_count_7d / 4.0) * 10.0)
                if youtube_views_7d and youtube_views_7d > 5000:
                    youtube_base += min(3.0, (youtube_views_7d / 20000.0) * 3.0)
                youtube_component = youtube_base
            else:
                # По умолчанию: умеренное влияние
                if has_steam_confirmation:
                    youtube_component = min(5.0, youtube_videos_count_7d * 0.5)
                else:
                    youtube_component = -min(3.0, youtube_videos_count_7d * 0.3)
        
        components.youtube_component = youtube_component
        
        # Пересчитываем score_momentum как сумму reddit + youtube (но не более 30)
        components.score_momentum = min(30.0, max(0.0, reddit_component) + max(0.0, youtube_component))
        
        return components
    
    def determine_verdict(
        self,
        score: float,
        flags: GameFlags,
        components: ScoreComponents
    ) -> str:
        """
        Определяет вердикт на основе анализа (на русском языке).
        Legacy метод для обратной совместимости.
        """
        if flags.is_evergreen_giant:
            return "Вечнозелёный гигант (исключён)"
        
        if score >= 60:
            if flags.has_real_growth and not flags.is_hype_spike:
                return "Сильный органический рост"
            elif flags.is_hype_spike:
                return "Хайп-всплеск"
            else:
                return "Высокий потенциал"
        elif score >= 40:
            if flags.is_new_release:
                return "Многообещающий новый релиз"
            elif flags.is_rediscovered_old_game:
                return "Переоткрытая старая игра"
            else:
                return "Умеренный рост"
        elif score >= 20:
            return "Слабый сигнал"
        else:
            return "Недостаточно данных"
    
    def make_verdict(
        self,
        score: float,
        steam_interpreted: Dict[str, Any],
        reddit_interpreted: Dict[str, Any],
        youtube_interpreted: Dict[str, Any],
        news_interpreted: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """
        Формирует вердикт на основе интерпретированных сигналов (Engine v5).
        
        Вердикты на русском языке:
        - "Ранний сигнал интереса, требуется подтверждение Steam"
        - "Подтверждённый рост с социальным ускорением"
        - "Инфоповод без устойчивого интереса"
        - "Хайп без конверсии в спрос"
        - "Устойчивый рост, инвестиционно интересно"
        """
        steam_confirmed = steam_interpreted["valid"]
        reddit_valid = reddit_interpreted["valid"]
        youtube_valid = youtube_interpreted["valid"]
        news_valid = news_interpreted["valid"]
        
        # 3B: Steam-only emerging - разрешаем emerging только на Steam
        if steam_confirmed and not reddit_valid and not youtube_valid:
            # Steam есть, но нет социальных сигналов
            if steam_interpreted["signal_strength"] in ["medium", "strong"]:
                return "Рост отзывов без социального подтверждения (Steam-only)"
            elif steam_interpreted["signal_strength"] == "weak":
                return "Слабый рост Steam без социальных сигналов"
        
        # Ранний сигнал: есть social, но нет Steam
        if not steam_confirmed and (reddit_valid or youtube_valid):
            return "Ранний сигнал интереса, требуется подтверждение Steam"
        
        # Хайп без конверсии: social есть, но Steam слабый
        if steam_confirmed and steam_interpreted["signal_strength"] == "weak":
            if reddit_valid or youtube_valid:
                # Проверяем risk_flags
                has_hype_risk = any("без Steam" in flag for flag in reddit_interpreted.get("risk_flags", []))
                if has_hype_risk:
                    return "Хайп без конверсии в спрос"
        
        # Инфоповод: только новости, без роста
        if news_valid and not steam_confirmed and not reddit_valid and not youtube_valid:
            return "Инфоповод без устойчивого интереса"
        
        # Высокий score
        if score >= 60:
            if steam_interpreted["signal_strength"] == "strong":
                if reddit_valid or youtube_valid:
                    return "Подтверждённый рост с социальным ускорением"
                else:
                    return "Устойчивый рост, инвестиционно интересно"
            else:
                return "Высокий потенциал"
        
        # Средний score
        if score >= 40:
            if context["stage"] == "early":
                return "Многообещающий новый релиз"
            elif context["stage"] == "mature" and steam_confirmed:
                return "Переоткрытая старая игра"
            else:
                return "Умеренный рост"
        
        # Низкий score
        if score >= 20:
            return "Слабый сигнал"
        
        return "Недостаточно данных"
    
    def build_explanation(
        self,
        steam_interpreted: Dict[str, Any],
        reddit_interpreted: Dict[str, Any],
        youtube_interpreted: Dict[str, Any],
        news_interpreted: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[str]:
        """
        Формирует объяснение на основе интерпретированных сигналов (Engine v5).
        
        Каждый элемент списка - отдельная причина попадания в emerging.
        """
        explanation = []
        
        # Steam причины
        if steam_interpreted["valid"]:
            explanation.append(steam_interpreted["reason"])
            if steam_interpreted.get("risk_flags"):
                for flag in steam_interpreted["risk_flags"]:
                    explanation.append(f"⚠️ {flag}")
        
        # Reddit причины
        if reddit_interpreted["valid"]:
            explanation.append(reddit_interpreted["reason"])
        elif reddit_interpreted.get("risk_flags"):
            # Показываем почему Reddit не засчитан
            for flag in reddit_interpreted["risk_flags"]:
                explanation.append(f"ℹ️ Reddit: {flag}")
        
        # YouTube причины
        if youtube_interpreted["valid"]:
            explanation.append(youtube_interpreted["reason"])
        elif youtube_interpreted.get("risk_flags"):
            for flag in youtube_interpreted["risk_flags"]:
                explanation.append(f"ℹ️ YouTube: {flag}")
        
        # News причины
        if news_interpreted["valid"]:
            explanation.append(news_interpreted["reason"])
        
        # Контекстные причины
        if context["stage"] == "early":
            explanation.append("Ранняя стадия: требуется подтверждение Steam")
        elif context["stage"] == "growth":
            explanation.append("Стадия роста: социальные сигналы усиливают импульс")
        
        if not explanation:
            explanation.append("Недостаточно данных для объяснения")
        
        return explanation[:5]  # Максимум 5 причин
    
    def build_why_now(
        self,
        steam_interpreted: Dict[str, Any],
        reddit_interpreted: Dict[str, Any],
        youtube_interpreted: Dict[str, Any],
        news_interpreted: Dict[str, Any],
        context: Dict[str, Any],
        evidence: List[Dict[str, Any]]
    ) -> str:
        """
        Формирует объяснение "почему сейчас" на основе интерпретированных сигналов (Engine v5).
        
        Использует реальные события из evidence и интерпретации сигналов.
        """
        reasons = []
        
        # Используем evidence если есть
        if evidence:
            by_source = {}
            for ev in evidence:
                source = ev.get("source", "unknown")
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(ev)
            
            # Steam News
            if "steam_news" in by_source and news_interpreted["valid"]:
                news_count = len(by_source["steam_news"])
                if news_count > 0:
                    top_news = by_source["steam_news"][0]
                    title_short = (top_news.get("title", "новость") or "новость")[:50]
                    if news_count == 1:
                        reasons.append(f"Вышло обновление: {title_short}")
                    else:
                        reasons.append(f"Вышло {news_count} обновлений за 7 дней")
            
            # Reddit
            if "reddit" in by_source:
                if reddit_interpreted["valid"]:
                    reddit_count = len(by_source["reddit"])
                    if reddit_interpreted.get("signal_strength") == "strong":
                        reasons.append(f"Рост обсуждений в Reddit (x{reddit_count}) подтверждает тренд")
                    else:
                        reasons.append(f"Обсуждения в Reddit: {reddit_count} постов")
                elif reddit_interpreted.get("risk_flags"):
                    reasons.append(f"Reddit: {reddit_interpreted['risk_flags'][0]}")
            
            # YouTube
            if "youtube" in by_source:
                if youtube_interpreted["valid"]:
                    yt_count = len(by_source["youtube"])
                    if youtube_interpreted.get("signal_strength") == "strong":
                        reasons.append(f"Рост видео на YouTube (x{yt_count}) усиливает импульс")
                    else:
                        reasons.append(f"Видео на YouTube: {yt_count} видео")
                elif youtube_interpreted.get("risk_flags"):
                    reasons.append(f"YouTube: {youtube_interpreted['risk_flags'][0]}")
        
        # Fallback: используем интерпретации
        if not reasons:
            if steam_interpreted["valid"]:
                reasons.append(steam_interpreted["reason"])
            if reddit_interpreted["valid"]:
                reasons.append(reddit_interpreted["reason"])
            if youtube_interpreted["valid"]:
                reasons.append(youtube_interpreted["reason"])
            if news_interpreted["valid"]:
                reasons.append(news_interpreted["reason"])
        
        # Добавляем временной контекст
        if context["stage"] == "early":
            reasons.append("Ранний сигнал (до подтверждения Steam)")
        elif context["stage"] == "growth":
            reasons.append("Стадия роста: множественные сигналы согласованы")
        
        if not reasons:
            reasons.append("Недостаточно данных для объяснения")
        
        return "; ".join(reasons[:3])  # Максимум 3 причины
    
    def compute_confidence_v5(
        self,
        steam_interpreted: Dict[str, Any],
        reddit_interpreted: Dict[str, Any],
        youtube_interpreted: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """
        Вычисляет confidence_score (0..100) на основе интерпретированных сигналов (Engine v5).
        """
        confidence = 20.0  # Базовая уверенность
        
        # Steam подтверждение
        if steam_interpreted["valid"]:
            confidence += 30.0
            if steam_interpreted["signal_strength"] == "strong":
                confidence += 20.0
            elif steam_interpreted["signal_strength"] == "medium":
                confidence += 10.0
        
        # External signals (только если есть Steam)
        if context["steam_confirmed"]:
            if reddit_interpreted["valid"]:
                confidence += 10.0
                if reddit_interpreted["signal_strength"] == "strong":
                    confidence += 5.0
            if youtube_interpreted["valid"]:
                confidence += 10.0
                if youtube_interpreted["signal_strength"] == "strong":
                    confidence += 5.0
        
        # Multi-source bonus
        sources_count = sum([
            steam_interpreted["valid"],
            reddit_interpreted["valid"],
            youtube_interpreted["valid"]
        ])
        if sources_count >= 2 and context["steam_confirmed"]:
            confidence += 10.0
        
        # Risk flags снижают confidence
        all_risk_flags = (
            steam_interpreted.get("risk_flags", []) +
            reddit_interpreted.get("risk_flags", []) +
            youtube_interpreted.get("risk_flags", [])
        )
        for flag in all_risk_flags:
            if "без Steam" in flag or "не засчитывается" in flag:
                confidence -= 5.0
        
        # Stage bonus
        if context["stage"] == "early" and reddit_interpreted["valid"]:
            confidence += 5.0  # Ранний сигнал важен
        
        return max(0.0, min(100.0, confidence))
    
    def determine_stage_v5(
        self,
        steam_interpreted: Dict[str, Any],
        reddit_interpreted: Dict[str, Any],
        youtube_interpreted: Dict[str, Any],
        context: Dict[str, Any],
        confidence_score: float
    ) -> str:
        """
        Определяет стадию (EARLY/CONFIRMING/BREAKOUT/FADING/NOISE) на основе интерпретаций (Engine v5).
        """
        steam_valid = steam_interpreted["valid"]
        reddit_valid = reddit_interpreted["valid"]
        youtube_valid = youtube_interpreted["valid"]
        
        # EARLY: внешние сигналы есть, Steam слабый/нет
        if not steam_valid and (reddit_valid or youtube_valid):
            return "EARLY"
        
        # BREAKOUT: сильный Steam + множественные сигналы + высокий confidence
        if steam_valid and steam_interpreted["signal_strength"] == "strong":
            sources_count = sum([reddit_valid, youtube_valid])
            if sources_count >= 1 and confidence_score >= 60:
                return "BREAKOUT"
        
        # CONFIRMING: Steam растёт + есть внешние сигналы
        if steam_valid and (reddit_valid or youtube_valid):
            return "CONFIRMING"
        
        # NOISE: слабые/разрозненные сигналы
        if confidence_score < 40 or (not steam_valid and not reddit_valid and not youtube_valid):
            return "NOISE"
        
        return "CONFIRMING"  # Default
    
    def analyze_game(
        self,
        steam_app_id: int,
        name: Optional[str],
        release_date: Optional[date],
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int],
        reviews_delta_1d: Optional[int],
        positive_ratio: Optional[float],
        tags: Optional[List[str]] = None,
        # Reddit signals
        reddit_posts_count_7d: Optional[int] = None,
        reddit_comments_count_7d: Optional[int] = None,
        reddit_velocity: Optional[int] = None,
        reddit_uniqueness: Optional[int] = None,
        # YouTube signals
        youtube_videos_count_7d: Optional[int] = None,
        youtube_views_7d: Optional[int] = None,
        youtube_velocity: Optional[int] = None,
        youtube_channel_quality: Optional[float] = None,
        # Steam News signals (Engine v4)
        steam_news_posts_7d: Optional[int] = None,
        steam_news_velocity: Optional[int] = None,
        # Engine v5: Debug mode
        debug: bool = False
    ) -> EmergingAnalysis:
        """
        Полный анализ игры для emerging (Engine v5: структурированная интерпретация).
        
        Архитектура:
        1. detect_context - определяет контекст игры
        2. collect_signals - собирает все сигналы
        3. interpret_signals - интерпретирует каждый источник
        4. combine_scores - комбинирует интерпретации
        5. make_verdict - формирует вердикт
        6. build_explanation - строит объяснение
        """
        try:
            # 1. Определяем контекст игры
            context = self.detect_context(
                release_date=release_date,
                reviews_total=reviews_total,
                reviews_delta_7d=reviews_delta_7d,
                reviews_delta_1d=reviews_delta_1d,
                positive_ratio=positive_ratio
            )
            
            # Если evergreen - исключаем сразу
            if context["is_evergreen"]:
                logger.debug(f"analyze_game: app_id={steam_app_id} excluded as evergreen")
                return self._create_evergreen_analysis(
                    steam_app_id=steam_app_id,
                    name=name,
                    context=context
                )
            
            # 2. Интерпретируем сигналы (Engine v5: структурированная интерпретация)
            steam_interpreted = self.interpret_steam(
                reviews_delta_7d=reviews_delta_7d,
                reviews_delta_1d=reviews_delta_1d,
                positive_ratio=positive_ratio,
                reviews_total=reviews_total,
                context=context
            )
            
            reddit_interpreted = self.interpret_reddit(
                reddit_posts_count_7d=reddit_posts_count_7d,
                reddit_velocity=reddit_velocity,
                reddit_comments_count_7d=reddit_comments_count_7d,
                reddit_uniqueness=reddit_uniqueness,
                context=context,
                steam_confirmed=context["steam_confirmed"]
            )
            
            youtube_interpreted = self.interpret_youtube(
                youtube_videos_count_7d=youtube_videos_count_7d,
                youtube_velocity=youtube_velocity,
                youtube_views_7d=youtube_views_7d,
                youtube_channel_quality=youtube_channel_quality,
                context=context,
                steam_confirmed=context["steam_confirmed"],
                reddit_confirmed=reddit_interpreted["valid"]
            )
            
            news_interpreted = self.interpret_news(
                steam_news_posts_7d=steam_news_posts_7d,
                steam_news_velocity=steam_news_velocity,
                context=context
            )
            
            # 3. Комбинируем скоры (Engine v5: строго разделённые компоненты)
            confirmation_score = steam_interpreted["score"] if steam_interpreted["valid"] else 0
            momentum_score = (
                (reddit_interpreted["score"] if reddit_interpreted["valid"] else 0) +
                (youtube_interpreted["score"] if youtube_interpreted["valid"] else 0)
            )
            catalyst_score = news_interpreted["score"] if news_interpreted["valid"] else 0
            
            # Финальный скор с весами (константы в Brain)
            total_score = (
                confirmation_score * self.SCORE_WEIGHT_CONFIRMATION +
                momentum_score * self.SCORE_WEIGHT_MOMENTUM +
                catalyst_score * self.SCORE_WEIGHT_CATALYST
            )
            
            # 4. Определяем вердикт
            verdict = self.make_verdict(
                score=total_score,
                steam_interpreted=steam_interpreted,
                reddit_interpreted=reddit_interpreted,
                youtube_interpreted=youtube_interpreted,
                news_interpreted=news_interpreted,
                context=context
            )
            
            # 5. Формируем объяснение
            explanation = self.build_explanation(
                steam_interpreted=steam_interpreted,
                reddit_interpreted=reddit_interpreted,
                youtube_interpreted=youtube_interpreted,
                news_interpreted=news_interpreted,
                context=context
            )
            
            # 6. Определяем signals_used
            signals_used = []
            if steam_interpreted["valid"]:
                signals_used.append("steam_reviews")
            if reddit_interpreted["valid"]:
                signals_used.append("reddit")
            if youtube_interpreted["valid"]:
                signals_used.append("youtube")
            if news_interpreted["valid"]:
                signals_used.append("steam_news")
            
            # 7. Вычисляем confidence
            confidence_score = self.compute_confidence_v5(
                steam_interpreted=steam_interpreted,
                reddit_interpreted=reddit_interpreted,
                youtube_interpreted=youtube_interpreted,
                context=context
            )
            
            confidence_level = "HIGH" if confidence_score >= 70 else ("MEDIUM" if confidence_score >= 40 else "LOW")
            
            # 8. Определяем stage
            stage = self.determine_stage_v5(
                steam_interpreted=steam_interpreted,
                reddit_interpreted=reddit_interpreted,
                youtube_interpreted=youtube_interpreted,
                context=context,
                confidence_score=confidence_score
            )
            
            # 9. Get evidence events
            evidence = self.get_evidence_events(steam_app_id)
            
            # 10. Build why_now
            why_now = self.build_why_now(
                steam_interpreted=steam_interpreted,
                reddit_interpreted=reddit_interpreted,
                youtube_interpreted=youtube_interpreted,
                news_interpreted=news_interpreted,
                context=context,
                evidence=evidence
            )
            
            # 11. Lifecycle и Growth Type (для совместимости с v5)
            lifecycle_stage = self.determine_lifecycle_stage(
                release_date=release_date,
                reviews_total=reviews_total,
                reviews_delta_7d=reviews_delta_7d,
                steam_news_posts_7d=steam_news_posts_7d,
                reddit_posts_count_7d=reddit_posts_count_7d,
                youtube_videos_count_7d=youtube_videos_count_7d
            )
            
            growth_type = self.determine_growth_type(
                reviews_delta_7d=reviews_delta_7d,
                reddit_posts_count_7d=reddit_posts_count_7d,
                reddit_velocity=reddit_velocity,
                youtube_videos_count_7d=youtube_videos_count_7d,
                youtube_velocity=youtube_velocity,
                steam_news_posts_7d=steam_news_posts_7d,
                steam_news_velocity=steam_news_velocity,
                signals_used=signals_used
            )
            
            # 12. WHY NOW v2
            why_now_v2 = self.generate_why_now_v2(
                reviews_total=reviews_total,
                reviews_delta_7d=reviews_delta_7d,
                positive_ratio=positive_ratio,
                reddit_posts_count_7d=reddit_posts_count_7d,
                reddit_velocity=reddit_velocity,
                youtube_videos_count_7d=youtube_videos_count_7d,
                youtube_velocity=youtube_velocity,
                steam_news_posts_7d=steam_news_posts_7d,
                steam_news_velocity=steam_news_velocity,
                signals_used=signals_used,
                evidence=evidence,
                lifecycle_stage=lifecycle_stage,
                growth_type=growth_type
            )
            
            # 13. Final rank score
            final_rank_score = total_score * (confidence_score / 100.0)
            
            # 14. Формируем ScoreComponents для обратной совместимости
            components = ScoreComponents()
            components.score_confirmation = confirmation_score
            components.score_momentum = momentum_score
            components.score_catalyst = catalyst_score
            components.reddit_component = reddit_interpreted["score"] if reddit_interpreted["valid"] else 0
            components.youtube_component = youtube_interpreted["score"] if youtube_interpreted["valid"] else 0
            
            # 15. Формируем GameFlags для обратной совместимости
            flags = self.compute_flags(
                steam_app_id=steam_app_id,
                release_date=release_date,
                reviews_total=reviews_total,
                reviews_delta_7d=reviews_delta_7d,
                reviews_delta_1d=reviews_delta_1d,
                positive_ratio=positive_ratio
            )
            
            # 16. Signal strengths для обратной совместимости
            signal_strengths = {
                "reviews_delta_7d": self.normalize_signal("reviews_delta_7d", reviews_delta_7d),
                "reviews_delta_1d": self.normalize_signal("reviews_delta_1d", reviews_delta_1d),
                "positive_ratio": self.normalize_signal("positive_ratio", positive_ratio)
            }
            
            logger.debug(
                f"analyze_game: app_id={steam_app_id}, score={total_score:.1f}, "
                f"verdict={verdict}, confidence={confidence_score:.1f}, stage={stage}"
            )
            
            # Engine v5: Debug trace (только при debug=True)
            debug_trace = None
            if debug:
                debug_trace = {
                    "context": context,
                    "interpreted": {
                        "steam": steam_interpreted,
                        "reddit": reddit_interpreted,
                        "youtube": youtube_interpreted,
                        "news": news_interpreted
                    },
                    "scores": {
                        "confirmation": confirmation_score,
                        "momentum": momentum_score,
                        "catalyst": catalyst_score,
                        "total": total_score
                    },
                    "filters": {
                        "evergreen_excluded": context.get("is_evergreen", False),
                        "reason": "Evergreen по контексту" if context.get("is_evergreen") else None
                    }
                }
            
            return EmergingAnalysis(
                steam_app_id=steam_app_id,
                name=name,
                emerging_score=round(total_score, 2),
                verdict=verdict,
                explanation=explanation,
                flags=flags,
                score_components=components,
                signal_strengths=signal_strengths,
                confidence_score=round(confidence_score, 1),
                confidence_level=confidence_level,
                stage=stage,
                why_now=why_now,
                signals_used=signals_used,
                evidence=evidence,
                lifecycle_stage=lifecycle_stage,
                growth_type=growth_type,
                why_now_v2=why_now_v2,
                final_rank_score=round(final_rank_score, 2),
                debug_trace=debug_trace
            )
            
        except Exception as e:
            logger.error(f"analyze_game error: app_id={steam_app_id}, error={e}", exc_info=True)
            # Возвращаем минимальный анализ при ошибке
            return self._create_error_analysis(steam_app_id=steam_app_id, name=name, error=str(e))
    
    def _create_evergreen_analysis(
        self,
        steam_app_id: int,
        name: Optional[str],
        context: Dict[str, Any]
    ) -> EmergingAnalysis:
        """Создаёт анализ для evergreen игры (исключённой)."""
        return EmergingAnalysis(
            steam_app_id=steam_app_id,
            name=name,
            emerging_score=0.0,
            verdict="Вечнозелёный гигант (исключён)",
            explanation=["Игра исключена как evergreen (старая игра с большим количеством отзывов без реального роста)"],
            flags=GameFlags(
                has_real_growth=False,
                is_evergreen_giant=True,
                is_hype_spike=False,
                is_low_quality_growth=False,
                is_new_release=False,
                is_rediscovered_old_game=False,
                reasons={"is_evergreen_giant": "Evergreen по контексту"}
            ),
            score_components=ScoreComponents(),
            signal_strengths={},
            confidence_score=0.0,
            confidence_level="LOW",
            stage="NOISE",
            why_now="Игра исключена как evergreen",
            signals_used=[],
            evidence=[],
            lifecycle_stage="MATURITY",
            growth_type="ORGANIC",
            why_now_v2={},
            final_rank_score=0.0,
            debug_trace=None
        )
    
    def _create_error_analysis(
        self,
        steam_app_id: int,
        name: Optional[str],
        error: str
    ) -> EmergingAnalysis:
        """Создаёт анализ при ошибке."""
        return EmergingAnalysis(
            steam_app_id=steam_app_id,
            name=name,
            emerging_score=0.0,
            verdict="Ошибка анализа",
            explanation=[f"Ошибка при анализе: {error}"],
            flags=GameFlags(
                has_real_growth=False,
                is_evergreen_giant=False,
                is_hype_spike=False,
                is_low_quality_growth=False,
                is_new_release=False,
                is_rediscovered_old_game=False,
                reasons={}
            ),
            score_components=ScoreComponents(),
            signal_strengths={},
            confidence_score=0.0,
            confidence_level="LOW",
            stage="NOISE",
            why_now="Ошибка анализа",
            signals_used=[],
            evidence=[],
            lifecycle_stage="MATURITY",
            growth_type="ORGANIC",
            why_now_v2={},
            final_rank_score=0.0
        )
        
        # 4. Вычисляем компоненты score (Engine v5: контекстное влияние + anti-hype)
        components = self.compute_score_components(
            signal_strengths=signal_strengths,
            flags=flags,
            release_date=release_date,
            reviews_total=reviews_total,
            reviews_delta_7d=reviews_delta_7d,
            reddit_posts_count_7d=reddit_posts_count_7d,
            reddit_comments_count_7d=reddit_comments_count_7d,
            reddit_velocity=reddit_velocity,
            reddit_uniqueness=reddit_uniqueness,
            youtube_videos_count_7d=youtube_videos_count_7d,
            youtube_views_7d=youtube_views_7d,
            youtube_velocity=youtube_velocity,
            youtube_channel_quality=youtube_channel_quality,
            steam_news_posts_7d=steam_news_posts_7d,
            steam_news_velocity=steam_news_velocity,
            lifecycle_stage=lifecycle_stage
        )
        
        # 4. Итоговый score
        emerging_score = max(0.0, components.total())
        
        # 5. Определяем вердикт
        verdict = self.determine_verdict(emerging_score, flags, components)
        
        # 6. Формируем объяснение
        explanation = []
        
        if reviews_delta_7d and reviews_delta_7d > 0:
            percentile = signal_strengths["reviews_delta_7d"].percentile
            if percentile:
                pct_str = f"топ {100 - percentile*100:.1f}%" if percentile > 0.95 else f"{percentile*100:.1f} процентиль"
                explanation.append(f"Отзывы +{reviews_delta_7d} за 7д ({pct_str})")
            else:
                explanation.append(f"Отзывы +{reviews_delta_7d} за 7д")
        
        if positive_ratio:
            explanation.append(f"Положительных отзывов {positive_ratio*100:.0f}%")
        
        if flags.has_real_growth:
            explanation.append("Устойчивый паттерн роста")
        
        if flags.is_new_release:
            explanation.append("Новый релиз (< 90 дней)")
        elif flags.is_rediscovered_old_game:
            explanation.append("Переоткрытая старая игра")
        
        if flags.is_hype_spike:
            explanation.append("Обнаружен единичный всплеск")
        
        if not explanation:
            explanation.append("Недостаточно данных сигналов")
        
        # Brain v3: Compute confidence, stage, signals_used, why_now
        signals_used = []
        if reviews_total or reviews_delta_7d or reviews_delta_1d or positive_ratio:
            signals_used.append("steam_reviews")
        if reddit_posts_count_7d or reddit_velocity:
            signals_used.append("reddit")
        if youtube_videos_count_7d or youtube_velocity:
            signals_used.append("youtube")
        if steam_news_posts_7d or steam_news_velocity:
            signals_used.append("steam_news")
        
        confidence_score = self.compute_confidence(
            signals_used=signals_used,
            reviews_total=reviews_total,
            reviews_delta_7d=reviews_delta_7d,
            positive_ratio=positive_ratio,
            reddit_velocity=reddit_velocity,
            youtube_velocity=youtube_velocity,
            # Engine v5: anti-hype параметры
            reddit_posts_count_7d=reddit_posts_count_7d,
            youtube_videos_count_7d=youtube_videos_count_7d,
            components=components
        )
        
        confidence_level = "HIGH" if confidence_score >= 70 else ("MEDIUM" if confidence_score >= 40 else "LOW")
        
        stage = self.determine_stage(
            reviews_delta_7d=reviews_delta_7d,
            reddit_velocity=reddit_velocity,
            youtube_velocity=youtube_velocity,
            signals_used=signals_used,
            confidence_score=confidence_score
        )
        
        # Engine v4: Get evidence events
        evidence = self.get_evidence_events(steam_app_id)
        
        why_now = self.generate_why_now(
            stage=stage,
            reviews_delta_7d=reviews_delta_7d,
            reddit_velocity=reddit_velocity,
            youtube_velocity=youtube_velocity,
            signals_used=signals_used,
            positive_ratio=positive_ratio,
            release_date=release_date,
            evidence=evidence
        )
        
        # Lifecycle Intelligence v5: определение жизненного цикла
        lifecycle_stage = self.determine_lifecycle_stage(
            release_date=release_date,
            reviews_total=reviews_total,
            reviews_delta_7d=reviews_delta_7d,
            steam_news_posts_7d=steam_news_posts_7d,
            reddit_posts_count_7d=reddit_posts_count_7d,
            youtube_videos_count_7d=youtube_videos_count_7d
        )
        
        # Anti-Hype Layer v5: определение типа роста
        growth_type = self.determine_growth_type(
            reviews_delta_7d=reviews_delta_7d,
            reddit_posts_count_7d=reddit_posts_count_7d,
            reddit_velocity=reddit_velocity,
            youtube_videos_count_7d=youtube_videos_count_7d,
            youtube_velocity=youtube_velocity,
            steam_news_posts_7d=steam_news_posts_7d,
            steam_news_velocity=steam_news_velocity,
            signals_used=signals_used
        )
        
        # WHY NOW v2: структурированное объяснение
        why_now_v2 = self.generate_why_now_v2(
            reviews_total=reviews_total,
            reviews_delta_7d=reviews_delta_7d,
            positive_ratio=positive_ratio,
            reddit_posts_count_7d=reddit_posts_count_7d,
            reddit_velocity=reddit_velocity,
            youtube_videos_count_7d=youtube_videos_count_7d,
            youtube_velocity=youtube_velocity,
            steam_news_posts_7d=steam_news_posts_7d,
            steam_news_velocity=steam_news_velocity,
            signals_used=signals_used,
            evidence=evidence,
            lifecycle_stage=lifecycle_stage,
            growth_type=growth_type
        )
        
        # Confidence как фактор ранжирования
        final_rank_score = emerging_score * (confidence_score / 100.0)
        
        return EmergingAnalysis(
            steam_app_id=steam_app_id,
            name=name,
            emerging_score=round(emerging_score, 2),
            verdict=verdict,
            explanation=explanation,
            flags=flags,
            score_components=components,
            signal_strengths=signal_strengths,
            confidence_score=round(confidence_score, 1),
            confidence_level=confidence_level,
            stage=stage,
            why_now=why_now,
            signals_used=signals_used,
            evidence=evidence,
            lifecycle_stage=lifecycle_stage,
            growth_type=growth_type,
            why_now_v2=why_now_v2,
            final_rank_score=round(final_rank_score, 2)
        )
    
    def compute_confidence(
        self,
        signals_used: List[str],
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int],
        positive_ratio: Optional[float],
        reddit_velocity: Optional[int],
        youtube_velocity: Optional[int],
        # Engine v5: anti-hype параметры
        reddit_posts_count_7d: Optional[int] = None,
        youtube_videos_count_7d: Optional[int] = None,
        components: Optional[ScoreComponents] = None
    ) -> float:
        """
        Вычисляет confidence_score (0..100) на основе доступных сигналов.
        Engine v5: включает anti-hype защиту (снижение при соц. шуме без Steam).
        """
        confidence = 20.0  # Базовая уверенность
        
        # Steam signals (подтверждение)
        has_steam_confirmation = False
        if reviews_total is not None and reviews_total > 0:
            confidence += 20.0
            has_steam_confirmation = True
        if positive_ratio is not None:
            confidence += 5.0
        
        if reviews_delta_7d is not None and reviews_delta_7d > 0:
            confidence += 15.0
            has_steam_confirmation = True
        
        # External signals (только если есть Steam подтверждение)
        has_social_signals = False
        if reddit_velocity and reddit_velocity > 0:
            if has_steam_confirmation:
                confidence += 10.0
            has_social_signals = True
        if youtube_velocity and youtube_velocity > 0:
            if has_steam_confirmation:
                confidence += 10.0
            has_social_signals = True
        
        # Multi-source bonus (только если есть Steam)
        if len(signals_used) >= 2 and has_steam_confirmation:
            confidence += 10.0
        
        # ===== Engine v5: Anti-Hype защита =====
        # Если есть соц. шум БЕЗ Steam подтверждения - снижаем confidence
        social_noise_without_steam = (
            (reddit_posts_count_7d and reddit_posts_count_7d > 0) or
            (youtube_videos_count_7d and youtube_videos_count_7d > 0)
        ) and not has_steam_confirmation
        
        if social_noise_without_steam:
            # Снижаем confidence на основе силы соц. сигналов
            social_strength = 0
            if reddit_posts_count_7d:
                social_strength += min(10, reddit_posts_count_7d)
            if youtube_videos_count_7d:
                social_strength += min(10, youtube_videos_count_7d)
            
            # Чем больше соц. шум без Steam, тем больше штраф
            hype_penalty = min(25.0, social_strength * 2.0)
            confidence -= hype_penalty
        
        # Дополнительный штраф если reddit/youtube компоненты отрицательные (anti-hype)
        if components:
            if components.reddit_component < 0:
                confidence -= abs(components.reddit_component) * 0.5
            if components.youtube_component < 0:
                confidence -= abs(components.youtube_component) * 0.5
        
        # Penalties
        if len(signals_used) == 1 and "steam_reviews" not in signals_used:
            # Только внешний источник без Steam подтверждения
            confidence -= 15.0
        
        if positive_ratio is not None and positive_ratio < 0.70:
            confidence -= 10.0
        
        return max(0.0, min(100.0, confidence))
    
    def determine_stage(
        self,
        reviews_delta_7d: Optional[int],
        reddit_velocity: Optional[int],
        youtube_velocity: Optional[int],
        signals_used: List[str],
        confidence_score: float
    ) -> str:
        """
        Определяет стадию (EARLY/CONFIRMING/BREAKOUT/FADING/NOISE).
        """
        has_steam = "steam_reviews" in signals_used
        has_reddit = "reddit" in signals_used
        has_youtube = "youtube" in signals_used
        
        # EARLY: внешние сигналы есть, Steam слабый/нет
        if (has_reddit or has_youtube) and (not has_steam or (reviews_delta_7d is None or reviews_delta_7d < 10)):
            return "EARLY"
        
        # BREAKOUT: высокий Steam рост + минимум 2 источника + высокий score
        if has_steam and reviews_delta_7d and reviews_delta_7d > 50 and len(signals_used) >= 2 and confidence_score >= 60:
            return "BREAKOUT"
        
        # CONFIRMING: Steam растёт + есть внешние сигналы
        if has_steam and reviews_delta_7d and reviews_delta_7d > 0 and (has_reddit or has_youtube):
            return "CONFIRMING"
        
        # FADING: сигналы слабеют (пока не реализовано из-за отсутствия истории)
        # TODO: добавить когда будет история по reddit/youtube
        
        # NOISE: слабые/разрозненные сигналы
        if confidence_score < 40 or (not has_steam and len(signals_used) == 1):
            return "NOISE"
        
        return "CONFIRMING"  # Default
    
    def get_evidence_events(self, steam_app_id: int, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Получить топ событий (evidence) для игры за последние 7 дней.
        Engine v4: возвращает реальные события с ссылками.
        """
        try:
            seven_days_ago = datetime.now() - timedelta(days=7)
            
            events = self.db.execute(
                text("""
                    SELECT 
                        source,
                        title,
                        url,
                        published_at,
                        metrics_json
                    FROM trends_raw_events
                    WHERE matched_steam_app_id = :app_id
                      AND published_at >= :seven_days_ago
                      AND match_confidence >= 0.80
                    ORDER BY published_at DESC
                    LIMIT :limit
                """),
                {
                    "app_id": steam_app_id,
                    "seven_days_ago": seven_days_ago,
                    "limit": limit
                }
            ).mappings().all()
            
            evidence = []
            for event in events:
                evidence.append({
                    "source": event["source"],
                    "title": event["title"] or "Без названия",
                    "url": event["url"] or "",
                    "published_at": event["published_at"].isoformat() if event["published_at"] else None,
                    "metrics": json.loads(event["metrics_json"]) if event.get("metrics_json") else {}
                })
            
            return evidence
            
        except Exception as e:
            logger.warning(f"get_evidence_events_error app_id={steam_app_id} error={e}")
            return []
    
    def generate_why_now(
        self,
        stage: str,
        reviews_delta_7d: Optional[int],
        reddit_velocity: Optional[int],
        youtube_velocity: Optional[int],
        signals_used: List[str],
        positive_ratio: Optional[float] = None,
        release_date: Optional[date] = None,
        evidence: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Генерирует человеческое объяснение "почему сейчас".
        Engine v4: использует реальные события из evidence.
        """
        if evidence is None:
            evidence = []
        
        reasons = []
        
        # Engine v4: Используем реальные события
        if evidence:
            # Группируем по источникам
            by_source = {}
            for ev in evidence:
                source = ev.get("source", "unknown")
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(ev)
            
            # Steam News
            if "steam_news" in by_source:
                news_count = len(by_source["steam_news"])
                if news_count > 0:
                    top_news = by_source["steam_news"][0]
                    title_short = (top_news.get("title", "новость") or "новость")[:50]
                    if news_count == 1:
                        reasons.append(f"Вышло обновление: {title_short}")
                    else:
                        reasons.append(f"Вышло {news_count} обновлений за 7 дней")
            
            # Reddit (Engine v5: объясняем роль с учётом anti-hype)
            if "reddit" in by_source:
                reddit_count = len(by_source["reddit"])
                if reddit_count > 0:
                    # Проверяем, есть ли Steam подтверждение
                    has_steam = reviews_delta_7d and reviews_delta_7d > 0
                    if has_steam:
                        if reddit_velocity and reddit_velocity > 0:
                            reasons.append(f"Рост обсуждений на Reddit подтверждает рост отзывов: +{reddit_velocity} постов")
                        else:
                            reasons.append(f"Обсуждения на Reddit ({reddit_count} постов) поддерживают тренд")
                    else:
                        # Anti-hype: соц. шум без Steam
                        reasons.append(f"Обсуждения в Reddit растут ({reddit_count} постов), но не подтверждаются ростом отзывов — сигнал снижен")
            
            # YouTube (Engine v5: объясняем роль с учётом anti-hype)
            if "youtube" in by_source:
                yt_count = len(by_source["youtube"])
                if yt_count > 0:
                    has_steam = reviews_delta_7d and reviews_delta_7d > 0
                    if has_steam:
                        if youtube_velocity and youtube_velocity > 0:
                            reasons.append(f"Рост видео на YouTube усиливает импульс: +{youtube_velocity} за 7 дней")
                        else:
                            reasons.append(f"Видео на YouTube ({yt_count}) поддерживают интерес")
                    else:
                        # Anti-hype: соц. шум без Steam
                        reasons.append(f"Видео на YouTube ({yt_count}), но нет подтверждения в Steam — возможен маркетинговый шум")
        
        # Fallback: если нет событий, используем сигналы
        if not reasons:
            if reviews_delta_7d and reviews_delta_7d > 0:
                reasons.append(f"Рост отзывов: +{reviews_delta_7d} за 7 дней")
            
            if reddit_velocity and reddit_velocity > 0:
                reasons.append(f"Рост обсуждений Reddit: +{reddit_velocity}")
            
            if youtube_velocity and youtube_velocity > 0:
                reasons.append(f"Рост видео YouTube: +{youtube_velocity}")
            
            if stage == "EARLY":
                reasons.append("Ранний сигнал (до подтверждения Steam)")
            elif stage == "BREAKOUT":
                reasons.append("Прорыв: высокий рост + множественные сигналы")
            elif stage == "CONFIRMING":
                reasons.append("Подтверждение: Steam рост + внешние сигналы")
        
        if not reasons:
            reasons.append("Недостаточно данных для объяснения")
        
        return "; ".join(reasons[:3])  # Максимум 3 причины
    
    def determine_lifecycle_stage(
        self,
        release_date: Optional[date],
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int],
        steam_news_posts_7d: Optional[int],
        reddit_posts_count_7d: Optional[int],
        youtube_videos_count_7d: Optional[int]
    ) -> str:
        """
        Определяет жизненный цикл игры (Lifecycle Intelligence v5).
        
        Возвращает: PRE_RELEASE, SOFT_LAUNCH, BREAKOUT, GROWTH, MATURITY, DECLINE, RELAUNCH_CANDIDATE
        """
        if not release_date:
            # Если нет даты релиза, используем эвристику по отзывам
            if reviews_total is None or reviews_total == 0:
                return "PRE_RELEASE"
            elif reviews_total < 100:
                return "SOFT_LAUNCH"
            else:
                return "MATURITY"
        
        days_since_release = (self.today - release_date).days
        years_since_release = days_since_release / 365.0
        
        # PRE_RELEASE: до релиза или первые дни
        if days_since_release < 0:
            return "PRE_RELEASE"
        
        # SOFT_LAUNCH: первые 30 дней, мало отзывов
        if days_since_release <= 30:
            if reviews_total is None or reviews_total < 50:
                return "SOFT_LAUNCH"
            # Если уже много отзывов - это BREAKOUT
            if reviews_total >= 50 and reviews_delta_7d and reviews_delta_7d > 20:
                return "BREAKOUT"
            return "SOFT_LAUNCH"
        
        # BREAKOUT: низкий total + резкий устойчивый рост
        if reviews_total and reviews_total < 1000:
            if reviews_delta_7d and reviews_delta_7d > 0:
                # Рост должен быть значительным относительно total
                growth_ratio = reviews_delta_7d / max(reviews_total, 1)
                if growth_ratio > 0.1:  # Рост >10% за 7 дней
                    return "BREAKOUT"
        
        # RELAUNCH_CANDIDATE: старая игра (>=2 лет) + новые внешние сигналы
        if years_since_release >= 2.0:
            has_external_catalysts = (
                (steam_news_posts_7d and steam_news_posts_7d > 0) or
                (reddit_posts_count_7d and reddit_posts_count_7d > 5) or
                (youtube_videos_count_7d and youtube_videos_count_7d > 3)
            )
            if has_external_catalysts and reviews_delta_7d and reviews_delta_7d > 0:
                return "RELAUNCH_CANDIDATE"
        
        # DECLINE: падение дельт без внешних сигналов
        if reviews_delta_7d is not None and reviews_delta_7d < -50:
            has_external_signals = (
                (steam_news_posts_7d and steam_news_posts_7d > 0) or
                (reddit_posts_count_7d and reddit_posts_count_7d > 0) or
                (youtube_videos_count_7d and youtube_videos_count_7d > 0)
            )
            if not has_external_signals:
                return "DECLINE"
        
        # GROWTH: высокий total + стабильный рост
        if reviews_total and reviews_total >= 1000:
            if reviews_delta_7d and reviews_delta_7d > 0:
                return "GROWTH"
        
        # MATURITY: по умолчанию для стабильных игр
        return "MATURITY"
    
    def determine_growth_type(
        self,
        reviews_delta_7d: Optional[int],
        reddit_posts_count_7d: Optional[int],
        reddit_velocity: Optional[int],
        youtube_videos_count_7d: Optional[int],
        youtube_velocity: Optional[int],
        steam_news_posts_7d: Optional[int],
        steam_news_velocity: Optional[int],
        signals_used: List[str]
    ) -> str:
        """
        Определяет тип роста (Anti-Hype Layer v5).
        
        Возвращает: ORGANIC, HYPE, NEWS_DRIVEN, PLATFORM_DRIVEN, MIXED
        """
        has_steam = "steam_reviews" in signals_used and reviews_delta_7d and reviews_delta_7d > 0
        has_reddit = (reddit_posts_count_7d and reddit_posts_count_7d > 0) or (reddit_velocity and reddit_velocity > 0)
        has_youtube = (youtube_videos_count_7d and youtube_videos_count_7d > 0) or (youtube_velocity and youtube_velocity > 0)
        has_news = (steam_news_posts_7d and steam_news_posts_7d > 0) or (steam_news_velocity and steam_news_velocity > 0)
        
        # HYPE: рост только в Reddit/YouTube без подтверждения Steam
        if not has_steam and (has_reddit or has_youtube):
            return "HYPE"
        
        # NEWS_DRIVEN: рост Steam + News, но без социальных сигналов
        if has_steam and has_news and not has_reddit and not has_youtube:
            return "NEWS_DRIVEN"
        
        # PLATFORM_DRIVEN: рост только в Steam, без внешних сигналов
        if has_steam and not has_news and not has_reddit and not has_youtube:
            return "PLATFORM_DRIVEN"
        
        # MIXED: несколько источников согласованы
        source_count = sum([has_steam, has_reddit, has_youtube, has_news])
        if source_count >= 2:
            return "MIXED"
        
        # ORGANIC: рост Steam с подтверждением из социальных сетей
        if has_steam and (has_reddit or has_youtube):
            return "ORGANIC"
        
        # По умолчанию
        return "ORGANIC"
    
    def generate_why_now_v2(
        self,
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int],
        positive_ratio: Optional[float],
        reddit_posts_count_7d: Optional[int],
        reddit_velocity: Optional[int],
        youtube_videos_count_7d: Optional[int],
        youtube_velocity: Optional[int],
        steam_news_posts_7d: Optional[int],
        steam_news_velocity: Optional[int],
        signals_used: List[str],
        evidence: Optional[List[Dict[str, Any]]],
        lifecycle_stage: str,
        growth_type: str
    ) -> Dict[str, Any]:
        """
        Генерирует структурированное объяснение "Почему сейчас" (WHY NOW v2).
        
        Возвращает объект с полями:
        - основной_триггер: главная причина
        - дополнительные_факторы: список факторов
        - аномалия: необычное поведение
        - риски: потенциальные проблемы
        - инвестиционное_окно_дней: оценка окна возможностей
        """
        result = {
            "основной_триггер": "",
            "дополнительные_факторы": [],
            "аномалия": "",
            "риски": "",
            "инвестиционное_окно_дней": 0
        }
        
        if evidence is None:
            evidence = []
        
        # Определяем основной триггер
        triggers = []
        
        # Steam News как основной триггер
        if steam_news_posts_7d and steam_news_posts_7d > 0:
            if evidence:
                news_events = [e for e in evidence if e.get("source") == "steam_news"]
                if news_events:
                    top_news = news_events[0]
                    title = top_news.get("title", "обновление") or "обновление"
                    triggers.append(f"Обновление в Steam: {title[:60]}")
        
        # Рост отзывов как триггер
        if reviews_delta_7d and reviews_delta_7d > 0:
            if reviews_total:
                growth_pct = (reviews_delta_7d / max(reviews_total, 1)) * 100
                if growth_pct > 10:
                    triggers.append(f"Рост отзывов на {growth_pct:.0f}% за 7 дней")
                else:
                    triggers.append(f"Рост отзывов: +{reviews_delta_7d} за 7 дней")
            else:
                triggers.append(f"Рост отзывов: +{reviews_delta_7d} за 7 дней")
        
        # Социальные сигналы как триггер
        if reddit_velocity and reddit_velocity > 0:
            triggers.append(f"Всплеск обсуждений в Reddit: +{reddit_velocity} постов")
        
        if youtube_velocity and youtube_velocity > 0:
            triggers.append(f"Рост видео на YouTube: +{youtube_velocity}")
        
        result["основной_триггер"] = triggers[0] if triggers else "Недостаточно данных для определения триггера"
        
        # Дополнительные факторы
        factors = []
        
        if positive_ratio and positive_ratio >= 0.8:
            factors.append(f"Высокое качество: {positive_ratio*100:.0f}% положительных отзывов")
        
        if lifecycle_stage == "BREAKOUT":
            factors.append("Стадия прорыва: игра набирает популярность")
        elif lifecycle_stage == "RELAUNCH_CANDIDATE":
            factors.append("Кандидат на перезапуск: старая игра с новыми сигналами")
        
        if growth_type == "ORGANIC":
            factors.append("Органический рост: подтверждён несколькими источниками")
        elif growth_type == "NEWS_DRIVEN":
            factors.append("Рост на новостях: обновления в Steam")
        
        if len(signals_used) >= 3:
            factors.append(f"Множественные сигналы: {len(signals_used)} источников")
        
        result["дополнительные_факторы"] = factors[:3]  # Максимум 3 фактора
        
        # Аномалия
        anomalies = []
        
        if reviews_delta_7d and reviews_total:
            growth_ratio = reviews_delta_7d / max(reviews_total, 1)
            if growth_ratio > 0.2:  # Рост >20% за 7 дней
                anomalies.append(f"Аномальный рост: +{growth_ratio*100:.0f}% за 7 дней (норма: <5%)")
        
        if reddit_velocity and reddit_velocity > 50:
            anomalies.append(f"Высокая активность в Reddit: +{reddit_velocity} постов за 7 дней")
        
        if lifecycle_stage == "RELAUNCH_CANDIDATE" and reviews_delta_7d and reviews_delta_7d > 0:
            anomalies.append("Возврат интереса к старой игре")
        
        result["аномалия"] = anomalies[0] if anomalies else ""
        
        # Риски
        risks = []
        
        if growth_type == "HYPE":
            risks.append("Риск хайпа: рост только в социальных сетях без подтверждения Steam")
        
        if not reddit_posts_count_7d and not youtube_videos_count_7d and not steam_news_posts_7d:
            risks.append("Нет внешних катализаторов: рост может быть временным")
        
        if positive_ratio and positive_ratio < 0.7:
            risks.append(f"Низкое качество: только {positive_ratio*100:.0f}% положительных отзывов")
        
        if len(signals_used) == 1:
            risks.append("Один источник данных: низкая надёжность сигнала")
        
        result["риски"] = "; ".join(risks[:2]) if risks else "Минимальные риски"
        
        # Инвестиционное окно (оценка в днях)
        window_days = 0
        
        if lifecycle_stage == "BREAKOUT":
            window_days = 14  # Короткое окно для прорыва
        elif lifecycle_stage == "GROWTH":
            window_days = 30  # Среднее окно для роста
        elif lifecycle_stage == "RELAUNCH_CANDIDATE":
            window_days = 21  # Окно для перезапуска
        elif growth_type == "NEWS_DRIVEN":
            window_days = 7  # Короткое окно для новостного роста
        elif growth_type == "ORGANIC":
            window_days = 45  # Длинное окно для органического роста
        else:
            window_days = 14  # По умолчанию
        
        result["инвестиционное_окно_дней"] = window_days
        
        return result
