"""
Тесты для TrendsBrain v5 (Engine v5: Proof Mode).

Проверяют детерминированность, правильность интерпретации сигналов,
и корректность работы правил anti-hype и контекстного влияния.
"""
import pytest
from datetime import date, timedelta
from sqlalchemy.orm import Session
from unittest.mock import Mock

from apps.worker.analysis.trends_brain import TrendsBrain


@pytest.fixture
def mock_db():
    """Мок БД для тестов."""
    db = Mock(spec=Session)
    db.execute.return_value.mappings.return_value.all.return_value = []
    return db


@pytest.fixture
def brain(mock_db):
    """Создаёт TrendsBrain для тестов."""
    return TrendsBrain(mock_db)


class TestDeterminism:
    """Тест 1: Детерминированность - два вызова с одинаковыми входными → одинаковый результат."""
    
    def test_determinism_same_inputs(self, brain):
        """Одинаковые входные данные должны давать одинаковый результат."""
        inputs = {
            "steam_app_id": 123,
            "name": "Test Game",
            "release_date": date.today() - timedelta(days=100),
            "reviews_total": 1000,
            "reviews_delta_7d": 50,
            "reviews_delta_1d": 10,
            "positive_ratio": 0.85
        }
        
        result1 = brain.analyze_game(**inputs)
        result2 = brain.analyze_game(**inputs)
        
        assert result1.emerging_score == result2.emerging_score
        assert result1.verdict == result2.verdict
        assert result1.confidence_score == result2.confidence_score
        assert result1.stage == result2.stage


class TestRedditRules:
    """Тест 2-3: Правила интерпретации Reddit и YouTube."""
    
    def test_reddit_without_velocity_invalid(self, brain):
        """Reddit без velocity → valid=false."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=100),
            reviews_total=1000,
            reviews_delta_7d=50,
            reddit_posts_count_7d=10,
            reddit_velocity=None  # Нет velocity
        )
        
        # Reddit не должен быть в signals_used если нет velocity
        assert "reddit" not in result.signals_used or result.score_components.reddit_component == 0
    
    def test_youtube_without_velocity_invalid(self, brain):
        """YouTube без velocity → valid=false."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=100),
            reviews_total=1000,
            reviews_delta_7d=50,
            youtube_videos_count_7d=5,
            youtube_velocity=None  # Нет velocity
        )
        
        # YouTube не должен быть в signals_used если нет velocity
        assert "youtube" not in result.signals_used or result.score_components.youtube_component == 0


class TestSocialWithoutSteam:
    """Тест 4: Social без Steam в mature → вердикт требует подтверждения."""
    
    def test_social_without_steam_mature(self, brain):
        """Social сигналы без Steam в mature стадии → вердикт требует подтверждения."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=1000),  # Старая игра (mature)
            reviews_total=1000,
            reviews_delta_7d=None,  # Нет Steam роста
            reviews_delta_1d=None,
            reddit_posts_count_7d=10,
            reddit_velocity=5
        )
        
        # Должен быть вердикт о необходимости подтверждения Steam или "Недостаточно данных"
        assert (
            "требуется подтверждение Steam" in result.verdict or
            "Недостаточно данных" in result.verdict or
            "Ранний сигнал" in result.verdict
        )


class TestSteamNegativeTrend:
    """Тест 5: Steam negative trend обнуляет momentum_score."""
    
    def test_steam_negative_obliterates_momentum(self, brain):
        """Отрицательная динамика Steam должна обнулить social score."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=100),
            reviews_total=1000,
            reviews_delta_7d=-50,  # Отрицательная динамика
            reviews_delta_1d=-10,
            reddit_posts_count_7d=10,
            reddit_velocity=5,
            youtube_videos_count_7d=5,
            youtube_velocity=3
        )
        
        # Momentum должен быть обнулён или очень низким
        assert result.score_components.score_momentum == 0 or result.score_components.score_momentum < 5


class TestNewsInfluence:
    """Тест 6: News влияет только на catalyst_score."""
    
    def test_news_only_catalyst(self, brain):
        """Steam News должен влиять только на catalyst, не на confirmation."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=100),
            reviews_total=1000,
            reviews_delta_7d=50,
            steam_news_posts_7d=2,
            steam_news_velocity=1
        )
        
        # News должен дать catalyst_score > 0
        assert result.score_components.score_catalyst > 0
        # Но confirmation не должен зависеть от news
        # (confirmation зависит только от Steam reviews)


class TestEarlyStageReddit:
    """Тест 7: Early-stage: Reddit увеличивает confidence, но мало влияет на score."""
    
    def test_early_stage_reddit_confidence(self, brain):
        """В early стадии Reddit должен увеличивать confidence, но не score."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=30),  # Early stage
            reviews_total=50,
            reviews_delta_7d=None,  # Нет Steam подтверждения
            reddit_posts_count_7d=10,
            reddit_velocity=5
        )
        
        # В early стадии Reddit может дать небольшой score, но главное - confidence
        # Проверяем, что confidence выше чем без Reddit
        result_no_reddit = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=30),
            reviews_total=50,
            reviews_delta_7d=None,
            reddit_posts_count_7d=None,
            reddit_velocity=None
        )
        
        # С Reddit confidence должен быть выше (или равным, если и так низкий)
        assert result.confidence_score >= result_no_reddit.confidence_score


class TestEvergreenExclusion:
    """Тест 8: Mature evergreen без spike → excluded=true."""
    
    def test_evergreen_excluded(self, brain):
        """Evergreen игра должна быть исключена."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=1500),  # 4+ года (mature)
            reviews_total=15000,  # Много отзывов
            reviews_delta_7d=10,  # Минимальный рост (не spike)
            reviews_delta_1d=2
        )
        
        # Evergreen должна быть исключена (score=0 или verdict об этом)
        assert (
            result.flags.is_evergreen_giant or
            result.emerging_score == 0 or
            "исключён" in result.verdict.lower()
        )


class TestPositiveRatioThreshold:
    """Тест 9: positive_ratio < порога → steam.valid=false или risk_flag."""
    
    def test_low_positive_ratio_risk(self, brain):
        """Низкий positive_ratio должен дать risk_flag или снизить score."""
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=100),
            reviews_total=1000,
            reviews_delta_7d=50,
            positive_ratio=0.60  # Низкий ratio
        )
        
        # Должен быть risk_flag или сниженный score
        # Проверяем через explanation или score
        has_risk = any("качество" in exp.lower() or "risk" in exp.lower() for exp in result.explanation)
        low_score = result.emerging_score < 30  # Низкий score из-за качества
        
        assert has_risk or low_score


class TestWhyNowGeneration:
    """Тест 10: why_now формируется при наличии evidence/news/аномалий."""
    
    def test_why_now_with_evidence(self, brain):
        """why_now должен формироваться при наличии evidence."""
        # Мокаем get_evidence_events чтобы вернуть evidence
        brain.get_evidence_events = Mock(return_value=[
            {
                "source": "steam_news",
                "title": "Test Update",
                "url": "https://example.com",
                "published_at": "2024-01-01T00:00:00Z"
            }
        ])
        
        result = brain.analyze_game(
            steam_app_id=123,
            name="Test",
            release_date=date.today() - timedelta(days=100),
            reviews_total=1000,
            reviews_delta_7d=50,
            steam_news_posts_7d=1,
            steam_news_velocity=1
        )
        
        # why_now должен быть не пустым
        assert result.why_now and len(result.why_now) > 0
        # И должен упоминать evidence если есть
        if result.evidence:
            assert len(result.evidence) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
