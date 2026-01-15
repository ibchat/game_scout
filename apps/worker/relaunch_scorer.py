"""Relaunch scoring engine (MVP)
- score_app(app_data) is the public entrypoint used by Celery task
- minimal keyword-based signal extraction from reviews
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

from apps.worker.relaunch_config import RELAUNCH_CONFIG


class RelaunchScorer:
    def __init__(self) -> None:
        self.config = RELAUNCH_CONFIG
        self.weights = self.config["weights"]
        self.thresholds = self.config["thresholds"]

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    def score_app(self, app_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        app_data expected shape:
        {
          "name": str,
          "snapshot": dict|None,
          "reviews": list[dict],
          "ccu_series": list[dict]
        }
        """
        name = (app_data or {}).get("name", "Unknown")
        snapshot = (app_data or {}).get("snapshot") or {}
        reviews = (app_data or {}).get("reviews") or []

        aggregated_signals = self._aggregate_signals_from_reviews(reviews)

        # compute
        return self.compute_score(
            app_data={"name": name},
            snapshots=[snapshot] if snapshot else [],
            reviews=reviews,
            aggregated_signals=aggregated_signals,
        )

    # -------------------------------------------------------------------------
    # Core compute
    # -------------------------------------------------------------------------
    def compute_score(
        self,
        app_data: Dict[str, Any],
        snapshots: List[Dict[str, Any]],
        reviews: List[Dict[str, Any]],
        aggregated_signals: Dict[str, Any],
    ) -> Dict[str, Any]:
        latest_snapshot = snapshots[0] if snapshots else {}

        product_quality = self._score_product_quality(latest_snapshot, aggregated_signals)
        marketing_failure = self._score_marketing_failure(latest_snapshot, aggregated_signals, snapshots)
        genre_mismatch = self._score_genre_mismatch(aggregated_signals)
        latent_audience = self._score_latent_audience(latest_snapshot, reviews, aggregated_signals)
        dev_signal = self._score_dev_signal(latest_snapshot, aggregated_signals)

        relaunch_score = (
            product_quality * self.weights["product_quality"]
            + marketing_failure * self.weights["marketing_failure"]
            + genre_mismatch * self.weights["genre_mismatch"]
            + latent_audience * self.weights["latent_audience"]
            + dev_signal * self.weights["dev_signal"]
        )

        classification = self._classify_score(relaunch_score, aggregated_signals)
        failure_reasons = self._identify_failure_reasons(aggregated_signals)
        relaunch_angles = self._generate_relaunch_angles(
            failure_reasons, aggregated_signals, latest_snapshot, product_quality, marketing_failure, genre_mismatch
        )
        reasoning = self._generate_reasoning(
            app_data.get("name", "Unknown"),
            relaunch_score,
            classification,
            failure_reasons,
            relaunch_angles,
            product_quality,
            marketing_failure,
        )

        return {
            "relaunch_score": round(float(relaunch_score), 2),
            "classification": classification,
            "product_quality_score": round(float(product_quality), 2),
            "marketing_failure_score": round(float(marketing_failure), 2),
            "genre_mismatch_score": round(float(genre_mismatch), 2),
            "latent_audience_score": round(float(latent_audience), 2),
            "dev_signal_score": round(float(dev_signal), 2),
            "failure_reasons": failure_reasons,
            "relaunch_angles": relaunch_angles,
            "reasoning_text": reasoning,
            "broken_game_evidence": aggregated_signals.get("evidence", {}).get("broken_game", []),
            "marketing_fail_evidence": aggregated_signals.get("evidence", {}).get("marketing_fail", []),
            "genre_mismatch_evidence": aggregated_signals.get("evidence", {}).get("expectation_mismatch", []),
            "underrated_evidence": aggregated_signals.get("evidence", {}).get("underrated", []),
            "reviews_analyzed_count": aggregated_signals.get("total_reviews", 0),
            "avg_playtime_hours": self._calc_avg_playtime(reviews),
            "review_velocity_30d": self._calc_review_velocity(reviews, 30),
        }

    # -------------------------------------------------------------------------
    # Signals (MVP)
    # -------------------------------------------------------------------------
    def _aggregate_signals_from_reviews(self, reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(reviews) or 0
        if total == 0:
            return {"total_reviews": 0, "signal_ratios": {}, "evidence": {}}

        patterns = {
            "broken_game": re.compile(r"\b(bug|bugs|broken|crash|crashes|crashed|stuck|freeze|freezes|unplayable)\b", re.I),
            "marketing_fail": re.compile(r"\b(no one|nobody|underrated|hidden gem|deserves more|should be popular)\b", re.I),
            "expectation_mismatch": re.compile(r"\b(not what i expected|misleading|wrong genre|tag(s)? are wrong|marketing lied)\b", re.I),
            "underrated": re.compile(r"\b(underrated|hidden gem|deserves more)\b", re.I),
            "has_loop": re.compile(r"\b(addictive|loop|just one more|grind|replay)\b", re.I),
            "has_systems": re.compile(r"\b(build|craft|progression|systems|depth|mechanic(s)?)\b", re.I),
            "dev_positive": re.compile(r"\b(dev(s)?|developer|patch|update|active dev|listens)\b", re.I),
        }

        counts = {k: 0 for k in patterns.keys()}
        evidence: Dict[str, List[str]] = {k: [] for k in ["broken_game", "marketing_fail", "expectation_mismatch", "underrated"]}

        for r in reviews:
            txt = (r.get("review_text") or "").strip()
            if not txt:
                continue

            for key, rx in patterns.items():
                if rx.search(txt):
                    counts[key] += 1
                    if key in evidence and len(evidence[key]) < 5:
                        evidence[key].append(txt[:240])

        ratios = {k: (v / total) for k, v in counts.items()}
        return {"total_reviews": total, "signal_ratios": ratios, "evidence": evidence}

    # -------------------------------------------------------------------------
    # Scoring components
    # -------------------------------------------------------------------------
    def _score_product_quality(self, snapshot: Dict[str, Any], signals: Dict[str, Any]) -> float:
        score = 50.0

        recent_positive = snapshot.get("recent_reviews_positive_percent")
        if recent_positive is not None:
            if recent_positive >= 80:
                score += 30
            elif recent_positive >= 70:
                score += 20
            elif recent_positive >= 60:
                score += 10
            else:
                score -= 10

        broken_ratio = signals.get("signal_ratios", {}).get("broken_game", 0.0)
        if broken_ratio > self.thresholds["broken_ratio_reject"]:
            score -= 40
        elif broken_ratio > 0.03:
            score -= 20

        if signals.get("signal_ratios", {}).get("has_loop", 0.0) > 0.10:
            score += 10
        if signals.get("signal_ratios", {}).get("has_systems", 0.0) > 0.10:
            score += 10

        return max(0.0, min(100.0, score))

    def _score_marketing_failure(self, snapshot: Dict[str, Any], signals: Dict[str, Any], snapshots: List[Dict[str, Any]]) -> float:
        score = 0.0
        marketing_ratio = signals.get("signal_ratios", {}).get("marketing_fail", 0.0)
        if marketing_ratio > 0.15:
            score += 50
        elif marketing_ratio > 0.08:
            score += 30
        elif marketing_ratio > 0.03:
            score += 15

        underrated_ratio = signals.get("signal_ratios", {}).get("underrated", 0.0)
        if underrated_ratio > 0.10:
            score += 25
        elif underrated_ratio > 0.05:
            score += 15

        review_count = snapshot.get("all_reviews_count", 0) or 0
        positive_pct = snapshot.get("all_reviews_positive_percent", 0) or 0
        if review_count < 500 and positive_pct >= 75:
            score += 20

        return max(0.0, min(100.0, score))

    def _score_genre_mismatch(self, signals: Dict[str, Any]) -> float:
        mismatch_ratio = signals.get("signal_ratios", {}).get("expectation_mismatch", 0.0)
        if mismatch_ratio > 0.15:
            return 70.0
        if mismatch_ratio > 0.10:
            return 50.0
        if mismatch_ratio > 0.05:
            return 30.0
        return 0.0

    def _score_latent_audience(self, snapshot: Dict[str, Any], reviews: List[Dict[str, Any]], signals: Dict[str, Any]) -> float:
        score = 0.0
        avg_playtime = self._calc_avg_playtime(reviews)
        review_count = snapshot.get("all_reviews_count", 0) or 0

        if avg_playtime > 10 and review_count < 1000:
            score += 40
        elif avg_playtime > 5 and review_count < 500:
            score += 25

        loop_ratio = signals.get("signal_ratios", {}).get("has_loop", 0.0)
        if loop_ratio > 0.15:
            score += 30
        elif loop_ratio > 0.08:
            score += 20

        return max(0.0, min(100.0, score))

    def _score_dev_signal(self, snapshot: Dict[str, Any], signals: Dict[str, Any]) -> float:
        score = 50.0
        dev_positive_ratio = signals.get("signal_ratios", {}).get("dev_positive", 0.0)
        if dev_positive_ratio > 0.10:
            score += 40
        elif dev_positive_ratio > 0.05:
            score += 25
        return max(0.0, min(100.0, score))

    def _classify_score(self, score: float, signals: Dict[str, Any]) -> str:
        broken_ratio = signals.get("signal_ratios", {}).get("broken_game", 0.0)
        if broken_ratio > self.thresholds["broken_ratio_reject"]:
            return "rejected"
        if score >= self.thresholds["candidate_score_min"]:
            return "candidate"
        if score >= self.thresholds["watchlist_score_min"]:
            return "watchlist"
        return "rejected"

    def _identify_failure_reasons(self, signals: Dict[str, Any]) -> List[str]:
        reasons: List[str] = []
        ratios = signals.get("signal_ratios", {})
        if ratios.get("broken_game", 0.0) > 0.03:
            reasons.append("broken_game")
        if ratios.get("marketing_fail", 0.0) > 0.05:
            reasons.append("marketing_failure")
        if ratios.get("expectation_mismatch", 0.0) > 0.05:
            reasons.append("genre_mismatch")
        if ratios.get("underrated", 0.0) > 0.05:
            reasons.append("underrated")
        return reasons

    def _generate_relaunch_angles(self, reasons, signals, snapshot, product_score, marketing_score, mismatch_score):
        angles = []
        if marketing_score > 30 and product_score > 60:
            angles.append(
                {
                    "angle": "Marketing Reboot",
                    "confidence": min(0.95, marketing_score / 100),
                    "description": "Strong product with weak visibility. Relaunch with improved store presence.",
                    "tactics": ["Redesign store capsule", "Influencer campaign", "Community building"],
                }
            )
        if mismatch_score > 40:
            angles.append(
                {
                    "angle": "Genre Repositioning",
                    "confidence": min(0.90, mismatch_score / 100),
                    "description": "Players expected different genre. Retag and reposition.",
                    "tactics": ["Update Steam tags", "Clarify genre in description"],
                }
            )
        return angles[:3]

    def _generate_reasoning(self, name, score, classification, reasons, angles, product_score, marketing_score):
        parts = [f"{name} scores {score:.1f}/100 for relaunch potential ({classification})."]
        if reasons:
            parts.append(f"Primary failure modes: {', '.join(reasons)}.")
        parts.append(f"Product quality: {product_score:.0f}/100, Marketing failure: {marketing_score:.0f}/100.")
        if angles:
            parts.append(f"Recommended angle: {angles[0]['angle']}.")
        return " ".join(parts)

    def _calc_avg_playtime(self, reviews: List[Dict[str, Any]]) -> float:
        if not reviews:
            return 0.0
        total = sum(float(r.get("playtime_at_review_hours") or 0.0) for r in reviews)
        return float(total) / float(len(reviews))

    def _calc_review_velocity(self, reviews: List[Dict[str, Any]], days: int) -> float:
        if not reviews:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent = 0
        for r in reviews:
            ts = r.get("posted_at")
            if isinstance(ts, datetime) and ts > cutoff:
                recent += 1
        return float(recent)
