"""Pre-defined follow-up message templates, keyed by identifier."""

PRESETS = {
    'request_more_info': {
        'ar': 'نرجو توضيح إجابتك بمزيد من التفاصيل.',
        'en': 'Please clarify your answer with more detail.',
    },
    'verify_identity': {
        'ar': 'نحتاج للتحقق من هويتك. هل يمكنك تأكيد بياناتك؟',
        'en': 'We need to verify your identity. Could you confirm your details?',
    },
    'clarify_attachment': {
        'ar': 'المرفق غير واضح. هل يمكنك إعادة إرفاق نسخة أوضح؟',
        'en': 'The attachment is unclear. Could you re-upload a clearer version?',
    },
}
