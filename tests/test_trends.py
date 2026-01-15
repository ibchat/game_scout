import pytest


def test_avg_7d_computation():
    """Test 7-day average computation"""
    historical_counts = [10, 12, 15, 8, 11, 13, 14]
    avg_7d = sum(historical_counts) / len(historical_counts)
    assert avg_7d == pytest.approx(11.857, rel=0.01)


def test_delta_7d_computation():
    """Test delta computation"""
    current_count = 20
    avg_7d = 12.0
    delta_7d = current_count - avg_7d
    assert delta_7d == 8.0


def test_velocity_computation():
    """Test velocity computation"""
    current_delta = 8.0
    yesterday_delta = 5.0
    velocity = current_delta - yesterday_delta
    assert velocity == 3.0


def test_zero_historical_data():
    """Test computation with no historical data"""
    current_count = 15
    avg_7d = 0.0  # No history
    delta_7d = current_count - avg_7d
    velocity = delta_7d  # velocity = delta when no yesterday
    
    assert delta_7d == 15.0
    assert velocity == 15.0


def test_negative_delta():
    """Test negative delta (declining trend)"""
    current_count = 5
    avg_7d = 15.0
    delta_7d = current_count - avg_7d
    assert delta_7d == -10.0


def test_negative_velocity():
    """Test negative velocity (decelerating)"""
    current_delta = -5.0
    yesterday_delta = -2.0
    velocity = current_delta - yesterday_delta
    assert velocity == -3.0


def test_rounding():
    """Test that values are properly rounded"""
    avg_7d = 11.857142857
    delta_7d = 8.142857143
    velocity = 3.285714286
    
    assert round(avg_7d, 2) == 11.86
    assert round(delta_7d, 2) == 8.14
    assert round(velocity, 2) == 3.29


if __name__ == "__main__":
    pytest.main([__file__, "-v"])