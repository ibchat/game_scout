"""
Trends Brain - Investment Intelligence Engine
Нормализует сигналы, интерпретирует поведение рынка, объясняет решения.

Это "мозг" платформы, который превращает сырые данные в объяснимый инвестиционный интеллект.
"""
import logging
from datetime import date, timedelta
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
    """Компоненты emerging score"""
    growth_component: float = 0.0
    velocity_component: float = 0.0
    sentiment_component: float = 0.0
    novelty_component: float = 0.0
    penalty_component: float = 0.0
    
    # Новые компоненты для мультимодального скоринга
    early_signal_component: float = 0.0  # Reddit/YouTube как early signals
    confirmation_component: float = 0.0  # Steam как confirmation
    momentum_component: float = 0.0  # YouTube как momentum
    
    def total(self) -> float:
        return (
            self.growth_component +
            self.velocity_component +
            self.sentiment_component +
            self.novelty_component +
            self.early_signal_component +
            self.confirmation_component +
            self.momentum_component -
            self.penalty_component
        )


@dataclass
class EmergingAnalysis:
    """Полный анализ игры для emerging"""
    steam_app_id: int
    name: Optional[str]
    emerging_score: float
    verdict: str  # "Strong organic growth", "Hype spike", "Low quality growth", etc.
    explanation: List[str]
    flags: GameFlags
    score_components: ScoreComponents
    signal_strengths: Dict[str, SignalStrength]


class TrendsBrain:
    """Мозг платформы - нормализует сигналы и интерпретирует поведение рынка"""
    
    def __init__(self, db: Session):
        self.db = db
        self.today = date.today()
        self._distribution_cache: Optional[Dict[str, List[float]]] = None
    
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
        reviews_total: Optional[int]
    ) -> ScoreComponents:
        """
        Вычисляет компоненты emerging score.
        """
        components = ScoreComponents()
        
        # 1. Growth Component (0..40)
        # Основан на reviews_delta_7d
        delta_7d_strength = signal_strengths.get("reviews_delta_7d", SignalStrength(0.0))
        components.growth_component = delta_7d_strength.value * 40
        
        # 2. Velocity Component (0..20)
        # Основан на reviews_delta_1d (скорость изменения)
        delta_1d_strength = signal_strengths.get("reviews_delta_1d", SignalStrength(0.0))
        components.velocity_component = delta_1d_strength.value * 20
        
        # 3. Sentiment Component (0..20)
        # Основан на positive_ratio
        pos_ratio_strength = signal_strengths.get("positive_ratio", SignalStrength(0.0))
        components.sentiment_component = pos_ratio_strength.value * 20
        
        # 4. Novelty Component (0..10)
        # Бонус за новые релизы или переоткрытые старые игры
        if flags.is_new_release:
            components.novelty_component = 5.0
        elif flags.is_rediscovered_old_game:
            components.novelty_component = 3.0
        
        # 5. Penalty Component (вычитается)
        if flags.is_evergreen_giant:
            components.penalty_component = 100.0  # Исключаем полностью
        elif flags.is_hype_spike:
            components.penalty_component = 15.0  # Штраф за всплеск
        elif flags.is_low_quality_growth:
            components.penalty_component = 10.0  # Штраф за низкое качество
        
        return components
    
    def determine_verdict(
        self,
        score: float,
        flags: GameFlags,
        components: ScoreComponents
    ) -> str:
        """
        Определяет вердикт на основе анализа.
        """
        if flags.is_evergreen_giant:
            return "Evergreen giant (excluded)"
        
        if score >= 60:
            if flags.has_real_growth and not flags.is_hype_spike:
                return "Strong organic growth"
            elif flags.is_hype_spike:
                return "Hype spike"
            else:
                return "High score"
        elif score >= 40:
            if flags.is_new_release:
                return "Promising new release"
            elif flags.is_rediscovered_old_game:
                return "Rediscovered old game"
            else:
                return "Moderate growth"
        elif score >= 20:
            return "Weak signal"
        else:
            return "Limited data"
    
    def analyze_game(
        self,
        steam_app_id: int,
        name: Optional[str],
        release_date: Optional[date],
        reviews_total: Optional[int],
        reviews_delta_7d: Optional[int],
        reviews_delta_1d: Optional[int],
        positive_ratio: Optional[float],
        tags: Optional[List[str]] = None
    ) -> EmergingAnalysis:
        """
        Полный анализ игры для emerging.
        """
        # 1. Нормализуем сигналы
        signal_strengths = {
            "reviews_delta_7d": self.normalize_signal("reviews_delta_7d", reviews_delta_7d),
            "reviews_delta_1d": self.normalize_signal("reviews_delta_1d", reviews_delta_1d),
            "positive_ratio": self.normalize_signal("positive_ratio", positive_ratio)
        }
        
        # 2. Вычисляем флаги
        flags = self.compute_flags(
            steam_app_id=steam_app_id,
            release_date=release_date,
            reviews_total=reviews_total,
            reviews_delta_7d=reviews_delta_7d,
            reviews_delta_1d=reviews_delta_1d,
            positive_ratio=positive_ratio
        )
        
        # 3. Вычисляем компоненты score
        components = self.compute_score_components(
            signal_strengths=signal_strengths,
            flags=flags,
            release_date=release_date,
            reviews_total=reviews_total
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
                pct_str = f"top {100 - percentile*100:.1f}%" if percentile > 0.95 else f"{percentile*100:.1f} percentile"
                explanation.append(f"Reviews +{reviews_delta_7d} in 7d ({pct_str})")
            else:
                explanation.append(f"Reviews +{reviews_delta_7d} in 7d")
        
        if positive_ratio:
            explanation.append(f"Positive ratio {positive_ratio*100:.0f}%")
        
        if flags.has_real_growth:
            explanation.append("Sustained growth pattern")
        
        if flags.is_new_release:
            explanation.append("New release (< 90 days)")
        elif flags.is_rediscovered_old_game:
            explanation.append("Rediscovered old game")
        
        if flags.is_hype_spike:
            explanation.append("Single-day spike detected")
        
        if not explanation:
            explanation.append("Limited signal data")
        
        return EmergingAnalysis(
            steam_app_id=steam_app_id,
            name=name,
            emerging_score=round(emerging_score, 2),
            verdict=verdict,
            explanation=explanation,
            flags=flags,
            score_components=components,
            signal_strengths=signal_strengths
        )
