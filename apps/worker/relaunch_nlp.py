"""NLP classifier for review signals"""
import re
from typing import Dict
from apps.worker.relaunch_config import RELAUNCH_CONFIG

class ReviewClassifier:
    """Rule-based NLP classifier"""
    
    def __init__(self):
        self.phrases = RELAUNCH_CONFIG["phrases"]
        self._compile_patterns()
    
    def _compile_patterns(self):
        self.patterns = {}
        for category, phrases in self.phrases.items():
            patterns = [re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE) for phrase in phrases]
            self.patterns[category] = patterns
    
    def classify_review(self, review_text: str, is_positive: bool) -> Dict:
        text_lower = review_text.lower()
        
        signals = {
            "broken_game": False,
            "marketing_fail": False,
            "underrated": False,
            "expectation_mismatch": False,
            "has_loop": False,
            "has_systems": False,
            "dev_positive": False,
        }
        
        match_counts = {
            "broken_game": 0,
            "marketing_fail": 0,
            "underrated": 0,
            "expectation_mismatch": 0,
            "loop": 0,
            "systems": 0,
            "dev_positive": 0,
        }
        
        matches = {}
        
        for category, patterns in self.patterns.items():
            category_matches = []
            for pattern in patterns:
                found = pattern.findall(text_lower)
                if found:
                    match_counts[category] += len(found)
                    category_matches.extend(found)
            if category_matches:
                matches[category] = category_matches[:5]
        
        signals["broken_game"] = match_counts["broken_game"] >= 2
        signals["marketing_fail"] = match_counts["marketing_fail"] >= 1
        signals["underrated"] = match_counts["underrated"] >= 1
        signals["expectation_mismatch"] = match_counts["expectation_mismatch"] >= 1
        signals["has_loop"] = match_counts["loop"] >= 1
        signals["has_systems"] = match_counts["systems"] >= 1
        signals["dev_positive"] = match_counts["dev_positive"] >= 1
        
        sentiment_score = 0.5 if is_positive else -0.5
        if signals["broken_game"]:
            sentiment_score -= 0.3
        if signals["has_loop"]:
            sentiment_score += 0.3
        
        sentiment_score = max(-1.0, min(1.0, sentiment_score))
        
        return {
            "signals": signals,
            "sentiment_score": sentiment_score,
            "match_counts": match_counts,
            "matches": matches
        }
    
    def aggregate_signals(self, reviews):
        total = len(reviews)
        if total == 0:
            return {}
        
        signal_counts = {k: 0 for k in ["broken_game", "marketing_fail", "underrated", "expectation_mismatch", "has_loop", "has_systems", "dev_positive"]}
        evidence = {k: [] for k in ["broken_game", "marketing_fail", "underrated", "expectation_mismatch"]}
        avg_sentiment = 0.0
        
        for review in reviews:
            signals = review.get('signals', {})
            for key in signal_counts:
                if signals.get(key):
                    signal_counts[key] += 1
            avg_sentiment += review.get('sentiment_score', 0.0)
            
            review_text = review.get('review_text', '')
            if signals.get('broken_game') and len(evidence['broken_game']) < 5:
                evidence['broken_game'].append(review_text[:200])
            if signals.get('marketing_fail') and len(evidence['marketing_fail']) < 5:
                evidence['marketing_fail'].append(review_text[:200])
        
        avg_sentiment /= total
        ratios = {k: v / total for k, v in signal_counts.items()}
        
        return {
            "signal_counts": signal_counts,
            "signal_ratios": ratios,
            "evidence": evidence,
            "avg_sentiment": avg_sentiment,
            "total_reviews": total
        }
