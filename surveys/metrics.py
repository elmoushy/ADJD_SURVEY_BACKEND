# surveys/metrics.py
"""
Metrics calculation helpers for NPS and CSAT analytics.

Provides reusable functions for dynamic threshold calculation and distribution analysis.
"""

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple


def nps_thresholds(min_scale: int, max_scale: int) -> Tuple[int, int]:
    """
    Calculate dynamic NPS bucket thresholds based on scale range.
    
    Returns (detractor_max, passive_max) for categorization.
    
    Default 0-5 star scale (recommended for rating questions):
    - Detractors: 0-2 stars (unhappy customers)
    - Passives: 3-4 stars (satisfied but unenthusiastic)
    - Promoters: 5 stars (loyal advocates)
    
    For 0-10 scale:
    - Detractors: 0-6
    - Passives: 7-8
    - Promoters: 9-10
    
    Args:
        min_scale: Minimum value of the rating scale
        max_scale: Maximum value of the rating scale
    
    Returns:
        Tuple of (detractor_max, passive_max) for score classification
    
    Examples:
        >>> nps_thresholds(0, 5)
        (2, 4)  # detractors: 0-2, passives: 3-4, promoters: 5
        
        >>> nps_thresholds(0, 10)
        (6, 8)  # detractors: 0-6, passives: 7-8, promoters: 9-10
        
        >>> nps_thresholds(1, 5)
        (2, 4)  # detractors: 1-2, passives: 3-4, promoters: 5
    """
    span = max_scale - min_scale
    
    # Special handling for 0-5 scale (star ratings)
    if min_scale == 0 and max_scale == 5:
        return (2, 4)  # 0-2: Detractors, 3-4: Passives, 5: Promoters
    
    # Special handling for 1-5 scale
    if min_scale == 1 and max_scale == 5:
        return (2, 4)  # 1-2: Detractors, 3-4: Passives, 5: Promoters
    
    # For 0-10 scale (traditional NPS)
    if min_scale == 0 and max_scale == 10:
        return (6, 8)  # 0-6: Detractors, 7-8: Passives, 9-10: Promoters
    
    # For other custom scales, use percentile-based approach
    # Detractors: bottom ~40% of scale
    # Passives: middle ~40% of scale  
    # Promoters: top ~20% of scale
    det_max = math.floor(min_scale + 0.40 * span)
    pas_max = math.floor(min_scale + 0.80 * span)
    
    # Ensure non-overlap and within bounds
    det_max = min(det_max, max_scale - 2)
    pas_max = min(max(pas_max, det_max + 1), max_scale - 1)
    
    return det_max, pas_max


def nps_distribution(values: List[float], min_scale: int, max_scale: int) -> List[Dict]:
    """
    Calculate distribution of NPS scores across entire scale range.
    
    Returns list of {"score": int, "count": int, "pct": float} dicts for each
    score value from min_scale to max_scale.
    
    Args:
        values: List of numeric score values from survey responses
        min_scale: Minimum value of the rating scale
        max_scale: Maximum value of the rating scale
    
    Returns:
        List of dictionaries with score, count, and percentage for each scale value
    
    Example:
        >>> values = [0, 3, 3, 4, 5, 5, 5]
        >>> nps_distribution(values, 0, 5)
        [
            {"score": 0, "count": 1, "pct": 14.3},
            {"score": 1, "count": 0, "pct": 0.0},
            {"score": 2, "count": 0, "pct": 0.0},
            {"score": 3, "count": 2, "pct": 28.6},
            {"score": 4, "count": 1, "pct": 14.3},
            {"score": 5, "count": 3, "pct": 42.9}
        ]
    """
    # Initialize bins for each score value
    bins = {s: 0 for s in range(min_scale, max_scale + 1)}
    
    # Count occurrences of each score
    for v in values:
        # Round to nearest integer and ensure within range
        rounded_val = int(round(v))
        if min_scale <= rounded_val <= max_scale:
            bins[rounded_val] += 1
    
    # Calculate total (avoid division by zero)
    total = sum(bins.values()) or 1
    
    # Build distribution with percentages
    distribution = []
    for score, count in bins.items():
        # Use Decimal for precise percentage calculation
        pct = float(Decimal(100 * count / total).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
        distribution.append({
            "score": score,
            "count": count,
            "pct": pct
        })
    
    return distribution


def nps_interpretation(score: float) -> str:
    """
    Provide human-readable interpretation of NPS score.
    
    Standard NPS ranges:
    - Excellent: 70-100
    - Great: 50-69
    - Good: 30-49
    - Fair: 0-29
    - Needs Improvement: -100 to -1
    
    Args:
        score: NPS score (-100 to 100)
    
    Returns:
        String interpretation of the score
    """
    if score >= 70:
        return "Excellent - World class"
    elif score >= 50:
        return "Great - Above average"
    elif score >= 30:
        return "Good - Industry average"
    elif score >= 0:
        return "Fair - Needs improvement"
    else:
        return "Poor - Critical issues"


def csat_score(satisfied: int, neutral: int, dissatisfied: int) -> float:
    """
    Calculate CSAT score as percentage of satisfied customers.
    
    Standard CSAT formula: (Satisfied / Total) × 100
    
    Args:
        satisfied: Count of satisfied responses
        neutral: Count of neutral responses
        dissatisfied: Count of dissatisfied responses
    
    Returns:
        CSAT score as percentage (0-100)
    """
    total = satisfied + neutral + dissatisfied
    if total == 0:
        return 0.0
    
    # Use Decimal for precise calculation
    score = float(Decimal(100 * satisfied / total).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
    return score


def csat_interpretation(score: float) -> str:
    """
    Provide human-readable interpretation of CSAT score.
    
    Standard CSAT ranges:
    - Excellent: 85-100
    - Good: 70-84
    - Fair: 50-69
    - Poor: 0-49
    
    Args:
        score: CSAT score (0-100)
    
    Returns:
        String interpretation of the score
    """
    if score >= 85:
        return "Excellent - Highly satisfied"
    elif score >= 70:
        return "Good - Generally satisfied"
    elif score >= 50:
        return "Fair - Room for improvement"
    else:
        return "Poor - Action required"
