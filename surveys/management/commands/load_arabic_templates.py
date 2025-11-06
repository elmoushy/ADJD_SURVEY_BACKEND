"""
Management command to load Arabic predefined templates into the database.

Usage:
    python manage.py load_arabic_templates
"""

import json
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from surveys.models import SurveyTemplate, TemplateQuestion

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load Arabic predefined templates from predefined_templates_arabic.json into the database'

    def handle(self, *args, **options):
        """Load templates from JSON file"""
        try:
            # Load the JSON file
            json_file_path = 'predefined_templates_arabic.json'
            
            self.stdout.write(self.style.WARNING(f'Loading templates from {json_file_path}...'))
            
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            templates_created = 0
            questions_created = 0
            templates_updated = 0
            
            # Separate templates and questions
            template_data = [item for item in data if item['model'] == 'surveys.surveytemplate']
            question_data = [item for item in data if item['model'] == 'surveys.templatequestion']
            
            # First, create/update templates
            for template_item in template_data:
                template_id = template_item['pk']
                fields = template_item['fields']
                
                # Check if template already exists
                template, created = SurveyTemplate.objects.update_or_create(
                    id=template_id,
                    defaults={
                        'name': fields['name'],
                        'name_ar': fields.get('name_ar'),
                        'description': fields['description'],
                        'description_ar': fields.get('description_ar'),
                        'category': fields['category'],
                        'icon': fields.get('icon', 'fa-star'),
                        'preview_image': fields.get('preview_image'),
                        'is_predefined': fields.get('is_predefined', True),
                        'usage_count': fields.get('usage_count', 0),
                        'created_by': None,  # Predefined templates have no creator
                    }
                )
                
                if created:
                    templates_created += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ Created template: {fields["name"]}'))
                else:
                    templates_updated += 1
                    self.stdout.write(self.style.WARNING(f'⟳ Updated template: {fields["name"]}'))
            
            # Then, create/update questions
            for question_item in question_data:
                question_id = question_item['pk']
                fields = question_item['fields']
                
                try:
                    template = SurveyTemplate.objects.get(id=fields['template'])
                    
                    question, created = TemplateQuestion.objects.update_or_create(
                        id=question_id,
                        defaults={
                            'template': template,
                            'text': fields['text'],
                            'text_ar': fields.get('text_ar'),
                            'question_type': fields['question_type'],
                            'options': fields.get('options'),
                            'is_required': fields.get('is_required', False),
                            'order': fields.get('order', 1),
                            'placeholder': fields.get('placeholder'),
                            'placeholder_ar': fields.get('placeholder_ar'),
                        }
                    )
                    
                    if created:
                        questions_created += 1
                        self.stdout.write(f'  ✓ Created question: {fields["text"][:50]}...')
                    else:
                        self.stdout.write(f'  ⟳ Updated question: {fields["text"][:50]}...')
                        
                except SurveyTemplate.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'✗ Template {fields["template"]} not found for question {question_id}')
                    )
            
            # Summary
            self.stdout.write(self.style.SUCCESS('\n' + '='*60))
            self.stdout.write(self.style.SUCCESS('SUMMARY:'))
            self.stdout.write(self.style.SUCCESS(f'Templates created: {templates_created}'))
            self.stdout.write(self.style.WARNING(f'Templates updated: {templates_updated}'))
            self.stdout.write(self.style.SUCCESS(f'Questions created/updated: {questions_created}'))
            self.stdout.write(self.style.SUCCESS('='*60))
            
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'Error: {json_file_path} not found. Make sure the file exists in the project root.')
            )
        except json.JSONDecodeError as e:
            self.stdout.write(
                self.style.ERROR(f'Error parsing JSON file: {e}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Unexpected error: {e}')
            )
            logger.exception('Error loading Arabic templates')
