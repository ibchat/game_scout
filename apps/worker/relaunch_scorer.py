"""Relaunch scoring engine"""
from typing import Dict, List
from datetime import datetime, timedelta
from apps.worker.relaunch_config import RELAUNCH_CONFIG

class RelaunchScorer:
    """Calculate relaunch potential scores"""
    
    def __init__(self):
        self.config = RELAUNCH_CONFIG
        self.weights = self.config["weights"]
        self.thresholds = self.config["thresholds"]
    
    def compute_score(self, app_data: Dict, snapshots: List[Dict], reviews: List[Dict], aggregated_signals: Dict) -> Dict:
        """Compute comprehensive relaunch score"""
        
        latest_snapshot = snapshots[0] if snapshots else {}
        
        # Component scores
        product_quality = self._score_product_quality(latest_snapshot, aggregated_signals)
        marketing_failure = self._score_marketing_failure(latest_snapshot, aggregated_signals, snapshots)
        genre_mismatch = self._score_genre_mismatch(aggregated_signals)
        latent_audience = self._score_latent_audience(latest_snapshot, reviews, aggregated_signals)
        dev_signal = self._score_dev_signal(latest_snapshot, aggregated_signals)
        
        # Weighted score
        relaunch_score = (
            product_quality * self.weights["product_quality"] +
            marketing_failure * self.weights["marketing_failure"] +
            genre_mismatch * self.weights["genre_mismatch"] +
            latent_audience * self.weights["latent_audience"] +
            dev_signal * self.weights["dev_signal"]
        )
        
        classification = self._classify_score(relaunch_score, aggregated_signals)
        failure_reasons = self._identify_failure_reasons(aggregated_signals)
        relaunch_angles = self._generate_relaunch_angles(failure_reasons, aggregated_signals, latest_snapshot, product_quality, marketing_failure, genre_mismatch)
        reasoning = self._generate_reasoning(app_data.get('name', 'Unknown'), relaunch_score, classification, failure_reasons, relaunch_angles, product_quality, marketing_failure)
        
        return {
            "relaunch_score": round(relaunch_score, 2),
            "classification": classification,
            "product_quality_score": round(product_quality, 2),
            "marketing_failure_score": round(marketing_failure, 2),
            "genre_mismatch_score": round(genre_mismatch, 2),
            "latent_audience_score": round(latent_audience, 2),
            "dev_signal_score": round(dev_signal, 2),
            "failure_reasons": failure_reasons,
            "relaunch_angles": relaunch_angles,
            "reasoning_text": reasoning,
            "broken_game_evidence": aggregated_signals.get('evidence', {}).get('broken_game', []),
            "marketing_fail_evidence": aggregated_signals.get('evidence', {}).get('marketing_fail', []),
            "genre_mismatch_evidence": aggregated_signals.get('evidence', {}).get('expectation_mismatch', []),
            "underrated_evidence": aggregated_signals.get('evidence', {}).get('underrated', []),
            "reviews_analyzed_count": aggregated_signals.get('total_reviews', 0),
            "avg_playtime_hours": self._calc_avg_playtime(reviews),
            "review_velocity_30d": self._calc_review_velocity(reviews, 30)
        }
    
    def _score_product_quality(self, snapshot: Dict, signals: Dict) -> float:
        score = 50.0
        recent_positive = snapshot.get('recent_reviews_positive_percent')
        if recent_positive:
            if recent_positive >= 80: score += 30
            elif recent_positive >= 70: score += 20
            elif recent_positive >= 60: score += 10
            else: score -= 10
        
        broken_ratio = signals.get('signal_ratios', {}).get('broken_game', 0)
        if broken_ratio > self.thresholds['broken_ratio_reject']: score -= 40
        elif broken_ratio > 0.03: score -= 20
        
        if signals.get('signal_ratios', {}).get('has_loop', 0) > 0.1: score += 10
        if signals.get('signal_ratios', {}).get('has_systems', 0) > 0.1: score += 10
        
        return max(0, min(100, score))
    
    def _score_marketing_failure(self, snapshot: Dict, signals: Dict, snapshots: List[Dict]) -> float:
        score = 0.0
        marketing_ratio = signals.get('signal_ratios', {}).get('marketing_fail', 0)
        if marketing_ratio > 0.15: score += 50
        elif marketing_ratio > 0.08: score += 30
        elif marketing_ratio > 0.03: score += 15
        
        underrated_ratio = signals.get('signal_ratios', {}).get('underrated', 0)
        if underrated_ratio > 0.1: score += 25
        elif underrated_ratio > 0.05: score += 15
        
        review_count = snapshot.get('all_reviews_count', 0)
        positive_pct = snapshot.get('all_reviews_positive_percent', 0)
        if review_count < 500 and positive_pct >= 75: score += 20
        
        return max(0, min(100, score))
    
    def _score_genre_mismatch(self, signals: Dict) -> float:
        mismatch_ratio = signals.get('signal_ratios', {}).get('expectation_mismatch', 0)
        if mismatch_ratio > 0.15: return 70
        elif mismatch_ratio > 0.10: return 50
        elif mismatch_ratio > 0.05: return 30
        return 0
    
    def _score_latent_audience(self, snapshot: Dict, reviews: List[Dict], signals: Dict) -> float:
        score = 0.0
        avg_playtime = self._calc_avg_playtime(reviews)
        review_count = snapshot.get('all_reviews_count', 0)
        
        if avg_playtime > 10 and review_count < 1000: score += 40
        elif avg_playtime > 5 and review_count < 500: score += 25
        
        if signals.get('signal_ratios', {}).get('has_loop', 0) > 0.15: score += 30
        elif signals.get('signal_ratios', {}).get('has_loop', 0) > 0.08: score += 20
        
        return max(0, min(100, score))
    
    def _score_dev_signal(self, snapshot: Dict, signals: Dict) -> float:
        score = 50.0
        dev_positive_ratio = signals.get('signal_ratios', {}).get('dev_positive', 0)
        if dev_positive_ratio > 0.1: score += 40
        elif dev_positive_ratio > 0.05: score += 25
        return max(0, min(100, score))
    
    def _classify_score(self, score: float, signals: Dict) -> str:
        broken_ratio = signals.get('signal_ratios', {}).get('broken_game', 0)
        if broken_ratio > self.thresholds['broken_ratio_reject']: return 'rejected'
        if score >= self.thresholds['candidate_score_min']: return 'candidate'
        elif score >= self.thresholds['watchlist_score_min']: return 'watchlist'
        else: return 'rejected'
    
    def _identify_failure_reasons(self, signals: Dict) -> List[str]:
        reasons = []
        ratios = signals.get('signal_ratios', {})
        if ratios.get('broken_game', 0) > 0.03: reasons.append('broken_game')
        if ratios.get('marketing_fail', 0) > 0.05: reasons.append('marketing_failure')
        if ratios.get('expectation_mismatch', 0) > 0.05: reasons.append('genre_mismatch')
        if ratios.get('underrated', 0) > 0.05: reasons.append('underrated')
        return reasons
    
    def _generate_relaunch_angles(self, reasons, signals, snapshot, product_score, marketing_score, mismatch_score):
        angles = []
        if marketing_score > 30 and product_score > 60:
            angles.append({
                "angle": "Marketing Reboot",
                "confidence": min(0.95, marketing_score / 100),
                "description": "Strong product with poor visibility. Relaunch with improved store presence.",
                "tactics": ["Redesign store capsule", "Influencer campaign", "Community building"]
            })
        if mismatch_score > 40:
            angles.append({
                "angle": "Genre Repositioning",
                "confidence": min(0.90, mismatch_score / 100),
                "description": "Players expected different genre. Retag and reposition.",
                "tactics": ["Update Steam tags", "Clarify genre in description"]
            })
        return angles[:3]
    
    def _generate_reasoning(self, name, score, classification, reasons, angles, product_score, marketing_score):
        parts = [f"{name} scores {score:.1f}/100 for relaunch potential ({classification})."]
        if reasons: parts.append(f"Primary failure modes: {', '.join(reasons)}.")
        parts.append(f"Product quality: {product_score:.0f}/100, Marketing failure: {marketing_score:.0f}/100.")
        if angles: parts.append(f"Recommended angle: {angles[0]['angle']}.")
        return ' '.join(parts)
    
    def _calc_avg_playtime(self, reviews):
        if not reviews: return 0.0
        total = sum(r.get('playtime_at_review_hours', 0) for r in reviews)
        return total / len(reviews)
    
    def _calc_review_velocity(self, reviews, days):
        if not reviews: return 0.0
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent = [r for r in reviews if r.get('posted_at', datetime.min) > cutoff]
        return len(recent)
