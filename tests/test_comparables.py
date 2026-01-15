import pytest
from apps.worker.scoring.comparables import jaccard_similarity, tokenize


def test_jaccard_similarity_identical():
    """Test Jaccard with identical sets"""
    set1 = {"roguelike", "action", "indie"}
    set2 = {"roguelike", "action", "indie"}
    similarity = jaccard_similarity(set1, set2)
    assert similarity == 1.0


def test_jaccard_similarity_disjoint():
    """Test Jaccard with no overlap"""
    set1 = {"roguelike", "action"}
    set2 = {"puzzle", "strategy"}
    similarity = jaccard_similarity(set1, set2)
    assert similarity == 0.0


def test_jaccard_similarity_partial():
    """Test Jaccard with partial overlap"""
    set1 = {"roguelike", "action", "indie"}
    set2 = {"roguelike", "strategy", "indie"}
    # Intersection: 2 (roguelike, indie)
    # Union: 4 (roguelike, action, indie, strategy)
    similarity = jaccard_similarity(set1, set2)
    assert similarity == 0.5


def test_jaccard_empty_sets():
    """Test Jaccard with empty sets"""
    assert jaccard_similarity(set(), set()) == 0.0
    assert jaccard_similarity({"a"}, set()) == 0.0
    assert jaccard_similarity(set(), {"a"}) == 0.0


def test_tokenize_basic():
    """Test basic tokenization"""
    text = "This is a test game"
    tokens = tokenize(text)
    # Should exclude stopwords: this, is, a
    assert "test" in tokens
    assert "game" in tokens
    assert "this" not in tokens
    assert "is" not in tokens


def test_tokenize_mixed_case():
    """Test case normalization"""
    text = "Roguelike ACTION Game"
    tokens = tokenize(text)
    assert "roguelike" in tokens
    assert "action" in tokens
    assert "game" in tokens


def test_tokenize_with_punctuation():
    """Test punctuation handling"""
    text = "Fast-paced, action-packed roguelike!"
    tokens = tokenize(text)
    assert "fast" in tokens
    assert "paced" in tokens
    assert "action" in tokens
    assert "packed" in tokens
    assert "roguelike" in tokens


def test_tokenize_empty():
    """Test empty text"""
    tokens = tokenize("")
    assert len(tokens) == 0
    
    tokens = tokenize(None)
    assert len(tokens) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])