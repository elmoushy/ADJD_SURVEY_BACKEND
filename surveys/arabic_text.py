# surveys/arabic_text.py
"""
Comprehensive Arabic text normalization and classification utilities.

Provides robust Arabic language support for survey analytics:
- Full Unicode normalization (diacritics, hamza, alef, yaa, taa marbuta)
- Gulf dialect support (UAE/GCC expressions)
- Mixed language handling (Arabic + English)
- Multi-format number parsing (Arabic/Persian/English digits)
- Intent matching for NPS/CSAT classification
"""

import re
import unicodedata
from typing import Literal

# Digit translation tables
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

# Unicode ranges for diacritics and marks
# Includes: tashkeel (064B-065F), superscript alef (0670), Quranic marks (06D6-06ED), presentation forms (FE70-FE7F)
DIACRITICS = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED\uFE70-\uFE7F]')

# Tatweel (kashida) - Arabic text elongation character
TATWEEL = '\u0640'

# Zero-width characters that can cause matching issues
ZERO_WIDTH = re.compile(r'[\u200B-\u200D\uFEFF]')


def normalize_arabic(text: str, preserve_numbers: bool = False) -> str:
    """
    Comprehensive Arabic text normalization for robust matching.
    
    Handles:
    - All diacritical marks (tashkeel)
    - All hamza and alef variants
    - Yaa and taa marbuta variations
    - Arabic, Persian, and English digits
    - Zero-width characters
    - Arabic punctuation
    - Tatweel (kashida)
    
    Args:
        text: Input text to normalize
        preserve_numbers: If False (default), convert all digits to ASCII 0-9
    
    Returns:
        Normalized lowercase text with consistent Arabic forms
    """
    if not text:
        return ""
    
    # Convert to string and strip whitespace
    t = str(text).strip()
    
    # Remove zero-width characters first (can break other operations)
    t = ZERO_WIDTH.sub('', t)
    
    # Normalize Unicode to NFC form (canonical composition)
    # This ensures consistent representation of composed characters
    t = unicodedata.normalize('NFC', t)
    
    # Convert to lowercase (handles both Arabic and Latin)
    t = t.lower()
    
    # Remove tatweel (kashida) - elongation character
    t = t.replace(TATWEEL, '')
    
    # Remove all diacritics (tashkeel marks)
    t = DIACRITICS.sub('', t)
    
    # Normalize ALL alef forms to plain alef (ا)
    t = t.replace('أ', 'ا')  # Alef with hamza above
    t = t.replace('إ', 'ا')  # Alef with hamza below
    t = t.replace('آ', 'ا')  # Alef with madda
    t = t.replace('ٱ', 'ا')  # Alef wasla
    
    # Normalize ALL hamza forms
    t = t.replace('ؤ', 'و')  # Hamza on waw → waw
    t = t.replace('ئ', 'ي')  # Hamza on yaa → yaa
    t = t.replace('ء', '')   # Standalone hamza → remove
    
    # Normalize yaa forms
    t = t.replace('ى', 'ي')  # Alef maqsuura → yaa
    
    # Normalize taa marbuta → haa
    # Common confusion point in Arabic text
    t = t.replace('ة', 'ه')
    
    # Convert digits (Arabic and Persian) to ASCII
    if not preserve_numbers:
        t = t.translate(ARABIC_DIGITS)
        t = t.translate(PERSIAN_DIGITS)
    
    # Normalize Arabic punctuation to standard ASCII
    t = t.replace('؟', '?')  # Arabic question mark
    t = t.replace('،', ',')  # Arabic comma
    t = t.replace('؛', ';')  # Arabic semicolon
    
    # Collapse multiple spaces to single space
    t = re.sub(r'\s+', ' ', t).strip()
    
    # Remove leading/trailing punctuation
    t = t.strip('.,;:!?؟،؛')
    
    return t


def extract_number(text: str) -> float | None:
    """
    Extract numeric value from text, supporting Arabic, Persian, and English digits.
    
    Handles:
    - Arabic digits (٠-٩)
    - Persian digits (۰-۹)
    - English digits (0-9)
    - Mixed formats ("٩ من ١٠", "9/10", "٩.٥")
    - Spelled-out Arabic numbers (صفر to عشرة)
    - Decimal numbers
    - Negative numbers
    
    Args:
        text: Text potentially containing a number
    
    Returns:
        First number found as float, or None if no valid number
    """
    if not text:
        return None
    
    # Normalize all digits to English first
    normalized = str(text).translate(ARABIC_DIGITS).translate(PERSIAN_DIGITS)
    
    # Try to find decimal or integer number
    # Pattern: optional minus, digits, optional decimal point and more digits
    match = re.search(r'-?\d+\.?\d*', normalized)
    
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    
    # Try spelled-out Arabic numbers (basic 0-10)
    # Normalized to handle various spellings
    number_words = {
        'صفر': 0, 'واحد': 1, 'اثنان': 2, 'اثنين': 2, 
        'ثلاثه': 3, 'ثلاثة': 3, 'اربعه': 4, 'اربعة': 4,
        'خمسه': 5, 'خمسة': 5, 'سته': 6, 'ستة': 6,
        'سبعه': 7, 'سبعة': 7, 'ثمانيه': 8, 'ثمانية': 8,
        'تسعه': 9, 'تسعة': 9, 'عشره': 10, 'عشرة': 10
    }
    
    normalized_text = normalize_arabic(text)
    for word, num in number_words.items():
        if normalize_arabic(word) in normalized_text:
            return float(num)
    
    return None


def yes_no_normalize(text: str) -> Literal['yes', 'no'] | None:
    """
    Normalize yes/no answers with comprehensive Arabic support.
    
    Handles:
    - Formal Arabic (نعم, لا, أجل, كلا)
    - Informal/dialectal (اي, ايه, أكيد, طبعا)
    - Affirmative phrases (بكل تأكيد, موافق, تمام)
    - English (yes, no, ok, sure)
    - Numeric (1 = yes, 0 = no)
    - Boolean strings (true, false)
    
    Args:
        text: Answer text to classify
    
    Returns:
        'yes', 'no', or None if cannot determine
    """
    if not text:
        return None
    
    normalized = normalize_arabic(text)
    
    # Comprehensive YES patterns
    yes_patterns = {
        # Arabic formal
        'نعم', 'اجل', 'بلى',
        # Arabic informal/dialectal
        'اي', 'ايه', 'ايوا', 'اكيد', 'طبعا', 'طبع',
        # Affirmative phrases
        'بكل تاكيد', 'بالتاكيد', 'موافق', 'حسنا', 'تمام', 'صحيح',
        # English
        'yes', 'yeah', 'yep', 'ok', 'okay', 'sure', 'true',
        # Numeric
        '1'
    }
    
    # Comprehensive NO patterns
    no_patterns = {
        # Arabic formal
        'لا', 'كلا', 'ليس',
        # Arabic negative
        'ابدا', 'مستحيل', 'رفض', 'خطا',
        # Phrases
        'غير موافق', 'لست متاكد',
        # English
        'no', 'nope', 'nah', 'false',
        # Numeric
        '0'
    }
    
    # Check for matches (both exact and contains)
    for pattern in yes_patterns:
        if pattern in normalized or normalized in pattern:
            return 'yes'
    
    for pattern in no_patterns:
        if pattern in normalized or normalized in pattern:
            return 'no'
    
    return None


# Comprehensive keyword sets (all pre-normalized)

NPS_KEYWORDS_AR = {
    # Root verb forms (recommend/advise)
    'توصي', 'تنصح', 'ترشح', 'ترشيح', 'تزكي',
    'يوصي', 'ينصح', 'يرشح', 'نوصي', 'ننصح',
    
    # Probability/likelihood phrases
    'احتماليه التوصيه', 'احتمال التوصيه', 'احتمال ان توصي',
    'مدى احتماليه التوصيه', 'مدى احتمال ان تنصح',
    
    # Willingness/readiness phrases
    'مدى استعدادك للتوصيه', 'استعدادك للتوصيه',
    'مدى رغبتك في التوصيه', 'رغبتك في التوصيه',
    'استعدادك لترشيح', 'مدى استعدادك للترشيح',
    
    # Question forms (Do you recommend/advise?)
    'هل تنصح', 'هل توصي', 'هل ترشح',
    'هل ستوصي', 'هل ستنصح', 'هل سترشح',
    'هل يمكنك التوصيه', 'هل يمكن ان توصي',
    
    # Capability phrases
    'قابليه الترشيح', 'قابليه التوصيه',
    'امكانيه التوصيه', 'امكانيه الترشيح',
    
    # Referral/endorsement terms
    'تزكيه', 'تاييد', 'اقتراح', 'دعم'
}

NPS_KEYWORDS_EN = {
    'recommend', 'likely to recommend', 'likelihood to recommend',
    'would you recommend', 'willing to recommend',
    'refer', 'referral', 'endorse', 'suggest',
    'how likely', 'probability of recommending'
}

CSAT_KEYWORDS_AR = {
    # Satisfaction root forms
    'رضا', 'راض', 'راضي', 'رضاك', 'رضاء',
    'مرتاح', 'ارتياح', 'ارتياحك',
    
    # Happiness/contentment terms
    'سعيد', 'سعاده', 'سعادتك', 'مسرور',
    'مبسوط', 'فرحان', 'فرح', 'ابتهاج',
    
    # Gulf dialect satisfaction
    'مبسوط', 'منبسط', 'مستانس', 'مرتاح',
    
    # Evaluation/assessment terms
    'تقييم', 'تقييمك', 'تقدير', 'تقديرك',
    'رايك', 'رايك في', 'وجهه نظرك',
    
    # Quality terms
    'جوده', 'جوده الخدمه', 'مستوى الجوده',
    'نوعيه', 'مستوى',
    
    # Service/experience terms
    'الخدمه', 'خدمه', 'خدمتنا', 'خدماتنا',
    'تجربه', 'تجربتك', 'التجربه',
    'مستوى الخدمه', 'مستوى التجربه',
    
    # Impression/opinion
    'انطباع', 'انطباعك', 'راي', 'اعجاب'
}

CSAT_KEYWORDS_EN = {
    'satisf', 'satisfaction', 'happy', 'pleased',
    'content', 'experience', 'quality', 'service',
    'impression', 'opinion', 'rate', 'rating',
    'how satisfied', 'level of satisfaction'
}

# CSAT choice classification sets (normalized)

CSAT_SATISFIED = {
    # Arabic - Excellent tier
    'ممتاز', 'ممتاز للغايه', 'ممتاز جدا', 'متميز', 'استثنايي',
    'رايع', 'رايع جدا', 'خرافي', 'مذهل', 'عظيم',
    
    # Arabic - Very good tier
    'جيد جدا', 'جيد للغايه', 'حلو', 'حلو جدا',
    'طيب', 'كويس', 'كويس جدا', 'تمام',
    
    # Arabic - Good/Satisfied tier
    'جيد', 'حسن', 'لا باس', 'لا باس به',
    'راض', 'راضي', 'راضي جدا', 'راضي تماما',
    'مرتاح', 'مرتاح جدا', 'سعيد', 'مبسوط',
    
    # English
    'excellent', 'outstanding', 'exceptional', 'superb',
    'great', 'wonderful', 'fantastic', 'amazing',
    'very good', 'very satisfied', 'good', 'satisfied',
    'happy', 'pleased', 'delighted', 'content'
}

CSAT_NEUTRAL = {
    # Arabic - Neutral expressions
    'محايد', 'عادي', 'عادي جدا', 'متوسط',
    'مقبول', 'مقبول نوعا ما', 'لا باس', 'مش بطال',
    'وسط', 'معقول', 'ماشي', 'ماشي الحال',
    'كذا', 'هيك', 'يعني', 'نص نص',
    
    # English
    'neutral', 'average', 'mediocre', 'moderate',
    'okay', 'ok', 'fair', 'acceptable',
    'so-so', 'neither good nor bad', 'middle'
}

CSAT_DISSATISFIED = {
    # Arabic - Strongly dissatisfied
    'سيي جدا', 'سيي للغايه', 'فظيع', 'فظيع جدا',
    'كارثه', 'كارثي', 'مريع', 'بشع', 'مقرف',
    'غير مقبول', 'غير مقبول نهائيا', 'مرفوض',
    
    # Arabic - Dissatisfied
    'سيي', 'سيء', 'مش كويس', 'مو زين',
    'ضعيف', 'ضعيف جدا', 'رديء', 'ردي',
    'غير راض', 'غير راضي', 'غير راضي ابدا',
    'غير مرتاح', 'مش مبسوط', 'مو مرتاح',
    
    # Arabic - Emotional responses
    'مستاء', 'مستاء جدا', 'منزعج', 'منزعج جدا',
    'غاضب', 'زعلان', 'محبط', 'يائس',
    'محرج', 'مخيب للامال', 'مخيب للظن',
    
    # English
    'terrible', 'horrible', 'awful', 'atrocious',
    'very bad', 'very poor', 'extremely poor',
    'dissatisfied', 'very dissatisfied', 'highly dissatisfied',
    'poor', 'bad', 'unsatisfied', 'unhappy',
    'upset', 'frustrated', 'disappointed', 'annoyed'
}


def match_intent(text: str, keywords: set[str]) -> bool:
    """
    Check if normalized text matches any keyword from the set.
    
    Uses partial matching (substring) for flexibility.
    
    Args:
        text: Text to check
        keywords: Set of normalized keywords to match against
    
    Returns:
        True if any keyword found in text
    """
    if not text:
        return False
    
    normalized = normalize_arabic(text)
    return any(keyword in normalized for keyword in keywords)


def classify_csat_choice(answer_text: str) -> Literal['satisfied', 'neutral', 'dissatisfied', 'unknown']:
    """
    Classify a choice answer as satisfied, neutral, or dissatisfied.
    
    Uses curated Arabic and English keyword sets for robust classification.
    
    Args:
        answer_text: The answer text to classify
    
    Returns:
        'satisfied', 'neutral', 'dissatisfied', or 'unknown'
    """
    if not answer_text:
        return 'unknown'
    
    normalized = normalize_arabic(answer_text)
    
    # Check in order: satisfied, dissatisfied, neutral (most specific first)
    if any(keyword in normalized for keyword in CSAT_SATISFIED):
        return 'satisfied'
    if any(keyword in normalized for keyword in CSAT_DISSATISFIED):
        return 'dissatisfied'
    if any(keyword in normalized for keyword in CSAT_NEUTRAL):
        return 'neutral'
    
    return 'unknown'
