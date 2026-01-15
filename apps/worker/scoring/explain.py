from apps.db.models import Pitch, Verdict
from typing import List, Dict, Tuple


def generate_explanations(
    pitch: Pitch,
    score_breakdown: Dict,
    comparables: List[Dict],
    verdict: Verdict
) -> Tuple[List[str], List[str], str]:
    """
    Generate why_yes, why_no, and next_step based on score breakdown
    """
    reasons = score_breakdown["reasons"]
    
    # Collect all positive signals
    all_positives = []
    for category, items in reasons.items():
        all_positives.extend(items)
    
    # Generate why_yes (top 3 strengths)
    why_yes = []
    if all_positives:
        # Prioritize by category importance
        priority_order = ["market", "team", "asymmetry", "hook", "steam"]
        for category in priority_order:
            if reasons.get(category):
                for reason in reasons[category][:1]:  # Take first from each
                    if len(why_yes) < 3:
                        why_yes.append(reason)
    
    # Pad if needed
    while len(why_yes) < 3 and all_positives:
        for item in all_positives:
            if item not in why_yes:
                why_yes.append(item)
                if len(why_yes) >= 3:
                    break
    
    # If still not enough, add generic positives
    if len(why_yes) < 3:
        if pitch.released_before:
            why_yes.append("Team has shipping experience")
        if pitch.team_size <= 3:
            why_yes.append("Small focused team")
        if pitch.timeline_months <= 18:
            why_yes.append("Reasonable timeline")
    
    why_yes = why_yes[:3]
    
    # Generate why_no (top 3 risks/gaps)
    why_no = []
    
    if score_breakdown["score_hook"] < 15:
        if not pitch.video_link:
            why_no.append("No video showcase provided")
        if not pitch.build_link:
            why_no.append("No playable build available")
        if not pitch.hook_one_liner:
            why_no.append("Missing clear hook statement")
    
    if score_breakdown["score_market"] < 15:
        if not pitch.tags or len(pitch.tags) < 3:
            why_no.append("Insufficient market positioning (tags)")
        else:
            why_no.append("Limited alignment with current market trends")
    
    if score_breakdown["score_team"] < 12:
        if not pitch.released_before:
            why_no.append("No prior shipping experience")
        if pitch.timeline_months > 18:
            why_no.append("Extended timeline increases risk")
    
    if score_breakdown["score_steam"] < 12:
        why_no.append("Steam readiness unclear")
    
    if not comparables or len(comparables) < 5:
        why_no.append("Limited comparable market validation")
    
    # Ensure we have exactly 3
    if len(why_no) > 3:
        why_no = why_no[:3]
    elif len(why_no) < 3:
        # Add generic risks
        generic_risks = [
            "Market competition intensity unknown",
            "Monetization strategy needs validation",
            "User acquisition plan requires clarity"
        ]
        for risk in generic_risks:
            if len(why_no) >= 3:
                break
            if risk not in why_no:
                why_no.append(risk)
    
    why_no = why_no[:3]
    
    # Generate next_step based on verdict and gaps
    next_step = generate_next_step(pitch, score_breakdown, verdict)
    
    return why_yes, why_no, next_step


def generate_next_step(pitch: Pitch, score_breakdown: Dict, verdict: Verdict) -> str:
    """Generate actionable next step"""
    
    if verdict == Verdict.INVEST:
        return "Schedule investment discussion call to review terms"
    
    if verdict == Verdict.TALK:
        if not pitch.video_link and not pitch.build_link:
            return "Send 60s gameplay video and playable demo link"
        elif not pitch.build_link:
            return "Provide playable demo build for evaluation"
        else:
            return "Schedule 30min call to discuss market positioning"
    
    if verdict == Verdict.WATCH:
        if not pitch.video_link:
            return "Share video showcase when available"
        if score_breakdown["score_market"] < 10:
            return "Clarify target audience and market segment"
        return "Share progress update in 30 days"
    
    # PASS
    if not pitch.released_before:
        return "Focus on shipping first title to build track record"
    if score_breakdown["score_hook"] < 10:
        return "Refine pitch with clearer hook and video demo"
    return "Revisit when product has more market validation"