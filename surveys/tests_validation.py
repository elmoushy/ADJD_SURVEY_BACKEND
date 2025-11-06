"""
Test cases for answer validation feature.

Tests the automatic validation type detection and answer validation
for email, phone, number, and URL fields.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from surveys.models import Survey, Question
from surveys.validators import (
    validate_email, validate_phone, validate_number, 
    validate_url, validate_answer
)

User = get_user_model()


class ValidationTypeDetectionTests(TestCase):
    """Test automatic validation type detection from question text"""
    
    def setUp(self):
        """Set up test user and survey"""
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123',
            role='user'
        )
        self.survey = Survey.objects.create(
            title='Test Survey',
            description='Test Description',
            creator=self.user,
            visibility='AUTH'
        )
    
    def test_email_detection_arabic(self):
        """Test email validation detection from Arabic keywords"""
        question = Question.objects.create(
            survey=self.survey,
            text='ما هو البريد الإلكتروني الخاص بك؟',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'email')
    
    def test_email_detection_english(self):
        """Test email validation detection from English keywords"""
        question = Question.objects.create(
            survey=self.survey,
            text='What is your email address?',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'email')
    
    def test_phone_detection_arabic(self):
        """Test phone validation detection from Arabic keywords"""
        question = Question.objects.create(
            survey=self.survey,
            text='ما هو رقم الهاتف؟',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'phone')
    
    def test_phone_detection_english(self):
        """Test phone validation detection from English keywords"""
        question = Question.objects.create(
            survey=self.survey,
            text='What is your phone number?',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'phone')
    
    def test_number_detection_arabic(self):
        """Test number validation detection from Arabic keywords"""
        question = Question.objects.create(
            survey=self.survey,
            text='كم عدد الموظفين؟',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'number')
    
    def test_url_detection_arabic(self):
        """Test URL validation detection from Arabic keywords"""
        question = Question.objects.create(
            survey=self.survey,
            text='ما هو رابط الموقع؟',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'url')
    
    def test_no_detection_for_generic_text(self):
        """Test that generic questions don't trigger validation"""
        question = Question.objects.create(
            survey=self.survey,
            text='What is your name?',
            question_type='text',
            order=1
        )
        self.assertEqual(question.validation_type, 'none')
    
    def test_manual_override(self):
        """Test that manually set validation_type is preserved"""
        question = Question.objects.create(
            survey=self.survey,
            text='Generic question',
            question_type='text',
            validation_type='email',  # Manually set
            order=1
        )
        self.assertEqual(question.validation_type, 'email')


class EmailValidationTests(TestCase):
    """Test email address validation"""
    
    def test_valid_email(self):
        """Test valid email addresses"""
        valid_emails = [
            'user@example.com',
            'test.user@domain.co.uk',
            'name+tag@example.org',
            'user123@test-domain.com'
        ]
        for email in valid_emails:
            is_valid, error = validate_email(email)
            self.assertTrue(is_valid, f"{email} should be valid")
            self.assertIsNone(error)
    
    def test_invalid_email(self):
        """Test invalid email addresses"""
        invalid_emails = [
            'invalid-email',
            '@example.com',
            'user@',
            'user@domain',
            'user domain@example.com'
        ]
        for email in invalid_emails:
            is_valid, error = validate_email(email)
            self.assertFalse(is_valid, f"{email} should be invalid")
            self.assertIsNotNone(error)
    
    def test_empty_email(self):
        """Test that empty email passes (handled by is_required)"""
        is_valid, error = validate_email('')
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class PhoneValidationTests(TestCase):
    """Test phone number validation"""
    
    def test_valid_phone(self):
        """Test valid phone numbers"""
        valid_phones = [
            '+971501234567',
            '971501234567',
            '0501234567',
            '501234567',
            '+1 234 567 8900',  # Spaces removed
            '+44-20-1234-5678'  # Dashes removed
        ]
        for phone in valid_phones:
            is_valid, error = validate_phone(phone)
            self.assertTrue(is_valid, f"{phone} should be valid")
            self.assertIsNone(error)
    
    def test_invalid_phone(self):
        """Test invalid phone numbers"""
        invalid_phones = [
            'abc123',
            '12-abc-34',
            'phone number',
            '123',  # Too short
            '12345678901234567890'  # Too long
        ]
        for phone in invalid_phones:
            is_valid, error = validate_phone(phone)
            self.assertFalse(is_valid, f"{phone} should be invalid")
            self.assertIsNotNone(error)
    
    def test_empty_phone(self):
        """Test that empty phone passes (handled by is_required)"""
        is_valid, error = validate_phone('')
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class NumberValidationTests(TestCase):
    """Test numeric validation"""
    
    def test_valid_numbers(self):
        """Test valid numbers"""
        valid_numbers = [
            '123',
            '123.45',
            '123,45',
            '-123',
            '-123.45',
            '0',
            '0.5'
        ]
        for number in valid_numbers:
            is_valid, error = validate_number(number)
            self.assertTrue(is_valid, f"{number} should be valid")
            self.assertIsNone(error)
    
    def test_invalid_numbers(self):
        """Test invalid numbers"""
        invalid_numbers = [
            'abc',
            '12.34.56',
            '12,34,56',
            'twelve',
            '12a34'
        ]
        for number in invalid_numbers:
            is_valid, error = validate_number(number)
            self.assertFalse(is_valid, f"{number} should be invalid")
            self.assertIsNotNone(error)
    
    def test_empty_number(self):
        """Test that empty number passes (handled by is_required)"""
        is_valid, error = validate_number('')
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class URLValidationTests(TestCase):
    """Test URL validation"""
    
    def test_valid_urls(self):
        """Test valid URLs"""
        valid_urls = [
            'https://example.com',
            'http://www.example.com',
            'https://example.com/path/to/page',
            'http://example.com:8080',
            'https://sub.example.co.uk'
        ]
        for url in valid_urls:
            is_valid, error = validate_url(url)
            self.assertTrue(is_valid, f"{url} should be valid")
            self.assertIsNone(error)
    
    def test_invalid_urls(self):
        """Test invalid URLs"""
        invalid_urls = [
            'not-a-url',
            'example.com',  # Missing protocol
            'ftp://example.com',  # Invalid protocol
            'http:/example.com',  # Missing slash
        ]
        for url in invalid_urls:
            is_valid, error = validate_url(url)
            self.assertFalse(is_valid, f"{url} should be invalid")
            self.assertIsNotNone(error)
    
    def test_empty_url(self):
        """Test that empty URL passes (handled by is_required)"""
        is_valid, error = validate_url('')
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class IntegratedAnswerValidationTests(TestCase):
    """Test integrated answer validation with Question model"""
    
    def setUp(self):
        """Set up test user and survey"""
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123',
            role='user'
        )
        self.survey = Survey.objects.create(
            title='Test Survey',
            description='Test Description',
            creator=self.user,
            visibility='AUTH'
        )
    
    def test_validate_email_answer(self):
        """Test email answer validation through Question"""
        question = Question.objects.create(
            survey=self.survey,
            text='ما هو البريد الإلكتروني؟',
            question_type='text',
            order=1
        )
        
        # Valid email
        is_valid, error = validate_answer(question, 'user@example.com')
        self.assertTrue(is_valid)
        
        # Invalid email
        is_valid, error = validate_answer(question, 'invalid-email')
        self.assertFalse(is_valid)
        self.assertIn('بريد', error)  # Arabic error message
    
    def test_validate_phone_answer(self):
        """Test phone answer validation through Question"""
        question = Question.objects.create(
            survey=self.survey,
            text='ما هو رقم الهاتف؟',
            question_type='text',
            order=1
        )
        
        # Valid phone
        is_valid, error = validate_answer(question, '+971501234567')
        self.assertTrue(is_valid)
        
        # Invalid phone
        is_valid, error = validate_answer(question, 'abc123')
        self.assertFalse(is_valid)
        self.assertIn('هاتف', error)  # Arabic error message
    
    def test_no_validation_for_choice_questions(self):
        """Test that validation is skipped for non-text questions"""
        question = Question.objects.create(
            survey=self.survey,
            text='Choose an option',
            question_type='single_choice',
            options='["Option 1", "Option 2"]',
            order=1
        )
        
        # Any answer should pass for choice questions
        is_valid, error = validate_answer(question, 'Option 1')
        self.assertTrue(is_valid)
