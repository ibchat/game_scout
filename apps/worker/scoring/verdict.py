from apps.db.models import Verdict


def assign_verdict(score_total: int) -> Verdict:
    """
    Assign verdict based on total score
    80-100: INVEST
    65-79: TALK
    50-64: WATCH
    <50: PASS
    """
    if score_total >= 80:
        return Verdict.INVEST
    elif score_total >= 65:
        return Verdict.TALK
    elif score_total >= 50:
        return Verdict.WATCH
    else:
        return Verdict.PASS