"""
Management command to populate predefined survey templates.
"""

from django.core.management.base import BaseCommand
from surveys.models import SurveyTemplate, TemplateQuestion
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Populate predefined survey templates'
    
    def handle(self, *args, **options):
        """Create predefined templates"""
        self.stdout.write(self.style.SUCCESS('Starting template population...'))
        
        # Define predefined templates
        templates_data = [
            {
                'id': 'contact-info',
                'name': 'Contact Information',
                'name_ar': 'معلومات الاتصال',
                'description': 'Collect contact details from respondents',
                'description_ar': 'جمع معلومات الاتصال من المستجيبين',
                'category': 'contact',
                'icon': 'fa-address-card',
                'questions': [
                    {
                        'text': 'What is your full name?',
                        'text_ar': 'ما هو اسمك الكامل؟',
                        'question_type': 'text',
                        'is_required': True,
                        'order': 1,
                        'placeholder': 'John Doe',
                        'placeholder_ar': 'أحمد محمد'
                    },
                    {
                        'text': 'What is your email address?',
                        'text_ar': 'ما هو عنوان بريدك الإلكتروني؟',
                        'question_type': 'text',
                        'is_required': True,
                        'order': 2,
                        'placeholder': 'john@example.com',
                        'placeholder_ar': 'ahmad@example.com'
                    },
                    {
                        'text': 'What is your phone number?',
                        'text_ar': 'ما هو رقم هاتفك؟',
                        'question_type': 'text',
                        'is_required': False,
                        'order': 3,
                        'placeholder': '+971 50 123 4567',
                        'placeholder_ar': '٩٧١ ٥٠ ١٢٣ ٤٥٦٧+'
                    }
                ]
            },
            {
                'id': 'rsvp',
                'name': 'RSVP',
                'name_ar': 'تأكيد الحضور',
                'description': 'Collect event attendance confirmation',
                'description_ar': 'جمع تأكيدات حضور الفعالية',
                'category': 'event',
                'icon': 'fa-calendar-check',
                'questions': [
                    {
                        'text': 'Will you be attending?',
                        'text_ar': 'هل ستحضر؟',
                        'question_type': 'yes_no',
                        'is_required': True,
                        'order': 1
                    },
                    {
                        'text': 'How many guests will you bring?',
                        'text_ar': 'كم عدد الضيوف الذين ستحضرهم؟',
                        'question_type': 'text',
                        'is_required': False,
                        'order': 2,
                        'placeholder': '0',
                        'placeholder_ar': '٠'
                    },
                    {
                        'text': 'Any dietary restrictions?',
                        'text_ar': 'هل لديك أي قيود غذائية؟',
                        'question_type': 'textarea',
                        'is_required': False,
                        'order': 3,
                        'placeholder': 'E.g., vegetarian, allergies...',
                        'placeholder_ar': 'مثال: نباتي، حساسية...'
                    }
                ]
            },
            {
                'id': 'party-invite',
                'name': 'Party Invite',
                'name_ar': 'دعوة حفلة',
                'description': 'Send party invitations and track responses',
                'description_ar': 'إرسال دعوات الحفلات وتتبع الردود',
                'category': 'event',
                'icon': 'fa-gift',
                'questions': [
                    {
                        'text': 'Can you make it to the party?',
                        'text_ar': 'هل يمكنك الحضور للحفلة؟',
                        'question_type': 'yes_no',
                        'is_required': True,
                        'order': 1
                    },
                    {
                        'text': 'Who will you be bringing?',
                        'text_ar': 'من ستحضر معك؟',
                        'question_type': 'text',
                        'is_required': False,
                        'order': 2
                    },
                    {
                        'text': 'What can you contribute?',
                        'text_ar': 'بماذا يمكنك المساهمة؟',
                        'question_type': 'single_choice',
                        'options': ['Food', 'Drinks', 'Music', 'Decorations', 'Nothing'],
                        'is_required': False,
                        'order': 3
                    }
                ]
            },
            {
                'id': 'tshirt-signup',
                'name': 'T-Shirt Sign Up',
                'name_ar': 'التسجيل للحصول على قميص',
                'description': 'Collect t-shirt size orders',
                'description_ar': 'جمع طلبات مقاسات القمصان',
                'category': 'registration',
                'icon': 'fa-tshirt',
                'questions': [
                    {
                        'text': 'What is your name?',
                        'text_ar': 'ما هو اسمك؟',
                        'question_type': 'text',
                        'is_required': True,
                        'order': 1
                    },
                    {
                        'text': 'Select your t-shirt size',
                        'text_ar': 'اختر مقاس القميص',
                        'question_type': 'single_choice',
                        'options': ['XS', 'S', 'M', 'L', 'XL', 'XXL'],
                        'is_required': True,
                        'order': 2
                    },
                    {
                        'text': 'Preferred color?',
                        'text_ar': 'اللون المفضل؟',
                        'question_type': 'single_choice',
                        'options': ['Black', 'White', 'Blue', 'Red', 'Green'],
                        'is_required': False,
                        'order': 3
                    }
                ]
            },
            {
                'id': 'event-registration',
                'name': 'Event Registration',
                'name_ar': 'تسجيل الفعالية',
                'description': 'Register attendees for events',
                'description_ar': 'تسجيل الحضور للفعاليات',
                'category': 'registration',
                'icon': 'fa-clipboard-list',
                'questions': [
                    {
                        'text': 'Full Name',
                        'text_ar': 'الاسم الكامل',
                        'question_type': 'text',
                        'is_required': True,
                        'order': 1
                    },
                    {
                        'text': 'Email Address',
                        'text_ar': 'عنوان البريد الإلكتروني',
                        'question_type': 'text',
                        'is_required': True,
                        'order': 2
                    },
                    {
                        'text': 'Organization/Company',
                        'text_ar': 'المنظمة/الشركة',
                        'question_type': 'text',
                        'is_required': False,
                        'order': 3
                    },
                    {
                        'text': 'Which sessions are you interested in?',
                        'text_ar': 'ما هي الجلسات التي تهتم بها؟',
                        'question_type': 'multiple_choice',
                        'options': ['Morning Session', 'Afternoon Session', 'Evening Session', 'Workshop', 'Networking'],
                        'is_required': True,
                        'order': 4
                    }
                ]
            },
            {
                'id': 'customer-feedback',
                'name': 'Customer Feedback',
                'name_ar': 'ملاحظات العملاء',
                'description': 'Gather customer feedback and satisfaction ratings',
                'description_ar': 'جمع ملاحظات العملاء وتقييمات الرضا',
                'category': 'feedback',
                'icon': 'fa-comments',
                'questions': [
                    {
                        'text': 'How satisfied are you with our service?',
                        'text_ar': 'ما مدى رضاك عن خدمتنا؟',
                        'question_type': 'rating',
                        'is_required': True,
                        'order': 1
                    },
                    {
                        'text': 'What did you like most?',
                        'text_ar': 'ما الذي أعجبك أكثر؟',
                        'question_type': 'textarea',
                        'is_required': False,
                        'order': 2
                    },
                    {
                        'text': 'What could we improve?',
                        'text_ar': 'ما الذي يمكننا تحسينه؟',
                        'question_type': 'textarea',
                        'is_required': False,
                        'order': 3
                    },
                    {
                        'text': 'Would you recommend us to others?',
                        'text_ar': 'هل ستوصي بنا للآخرين؟',
                        'question_type': 'yes_no',
                        'is_required': True,
                        'order': 4
                    }
                ]
            }
        ]
        
        created_count = 0
        updated_count = 0
        
        for template_data in templates_data:
            questions_data = template_data.pop('questions')
            template_id = template_data.pop('id')
            
            # Check if template already exists
            existing_templates = SurveyTemplate.objects.filter(
                name=template_data['name'],
                is_predefined=True
            )
            
            if existing_templates.exists():
                # Update existing template
                template = existing_templates.first()
                for key, value in template_data.items():
                    setattr(template, key, value)
                template.is_predefined = True
                template.save()
                
                # Delete old questions and create new ones
                template.questions.all().delete()
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'Updated template: {template.name}'))
            else:
                # Create new template
                template = SurveyTemplate.objects.create(
                    **template_data,
                    is_predefined=True,
                    created_by=None
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created template: {template.name}'))
            
            # Create questions
            for question_data in questions_data:
                TemplateQuestion.objects.create(
                    template=template,
                    **question_data
                )
            
            self.stdout.write(f'  Added {len(questions_data)} questions')
        
        self.stdout.write(self.style.SUCCESS(
            f'\nTemplate population complete!\n'
            f'Created: {created_count} templates\n'
            f'Updated: {updated_count} templates\n'
            f'Total: {created_count + updated_count} templates'
        ))
