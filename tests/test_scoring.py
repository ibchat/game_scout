import pytest
from db.models import Pitch, Verdict
from apps.worker.scoring.scoring_rules import (
    compute_hook_score,
    compute_team_score,
    compute_steam_score,
    compute_asymmetry_score,
)
from apps.worker.scoring.verdict import assign_verdict


def test_hook_score_full():
    """Test maximum hook score"""
    pitch = Pitch(
        dev_name="Test",
        email="test@test.com",
        team_size=2,
        released_before=True,
        timeline_months=12,
        pitch_text="x" * 200,
        hook_one_liner="Amazing game",
        video_link="https://youtube.com/watch",
        build_link="https://game.com/play",
        tags=[]
    )
    
    score, reasons = compute_hook_score(pitch)
    assert score == 25
    assert len(reasons) == 4


def test_hook_score_partial():
    """Test partial hook score"""
    pitch = Pitch(
        dev_name="Test",
        email="test@test.com",
        team_size=2,
        released_before=True,
        timeline_months=12,
        pitch_text="Short",
        video_link="https://youtube.com/watch",
        tags=[]
    )
    
    score, reasons = compute_hook_score(pitch)
    assert score == 7  # Only video


def test_team_score_experienced():
    """Test team score for experienced team"""
    pitch = Pitch(
        dev_name="Test",
        email="test@test.com",
        team_size=2,
        released_before=True,
        timeline_months=10,
        pitch_text="Test",
        tags=[]
    )
    
    score, reasons = compute_team_score(pitch)
    assert score == 20  # All bonuses
    assert len(reasons) == 3


def test_team_score_inexperienced():
    """Test team score for inexperienced team"""
    pitch = Pitch(
        dev_name="Test",
        email="test@test.com",
        team_size=5,
        released_before=False,
        timeline_months=24,
        pitch_text="Test",
        tags=[]
    )
    
    score, reasons = compute_team_score(pitch)
    assert score == 0


def test_steam_score_ready():
    """Test Steam readiness score"""
    pitch = Pitch(
        dev_name="Test",
        email="test@test.com",
        team_size=2,
        released_before=True,
        timeline_months=12,
        pitch_text="Test",
        build_link="https://game.com",
        video_link="https://video.com",
        tags=["action", "indie", "roguelike"]
    )
    
    score, reasons = compute_steam_score(pitch)
    assert score == 20


def test_asymmetry_score_upside():
    """Test asymmetry score with upside"""
    pitch = Pitch(
        dev_name="Test",
        email="test@test.com",
        team_size=2,
        released_before=True,
        timeline_months=10,
        pitch_text="Test",
        tags=[]
    )
    
    comparables = [
        {"reviews_total": 1500, "name": "Big Hit"}
    ]
    
    score, reasons = compute_asymmetry_score(pitch, comparables)
    assert score == 10  # Both bonuses


def test_verdict_assignment():
    """Test verdict assignment thresholds"""
    assert assign_verdict(85) == Verdict.INVEST
    assert assign_verdict(80) == Verdict.INVEST
    assert assign_verdict(70) == Verdict.TALK
    assert assign_verdict(65) == Verdict.TALK
    assert assign_verdict(55) == Verdict.WATCH
    assert assign_verdict(50) == Verdict.WATCH
    assert assign_verdict(45) == Verdict.PASS
    assert assign_verdict(0) == Verdict.PASS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])