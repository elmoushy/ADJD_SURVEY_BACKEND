"""
Tests for surveys app.

This module contains unit tests for models, views, permissions,
and serializers following Django testing best practices.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Survey, Question, Response, Answer, PublicAccessToken
from .encryption import surveys_data_encryption
import json

User = get_user_model()


class SurveyModelTest(TestCase):
    """Test cases for Survey model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_survey_creation(self):
        """Test creating a survey"""
        survey = Survey.objects.create(
            title='Test Survey',
            description='Test Description',
            creator=self.user,
            visibility='PRIVATE'
        )
        
        self.assertEqual(survey.title, 'Test Survey')
        self.assertEqual(survey.creator, self.user)
        self.assertEqual(survey.visibility, 'PRIVATE')
        self.assertIsNotNone(survey.title_hash)
    
    def test_encryption(self):
        """Test field encryption"""
        survey = Survey.objects.create(
            title='Encrypted Title',
            description='Encrypted Description',
            creator=self.user
        )
        
        # Retrieve from database to test decryption
        saved_survey = Survey.objects.get(id=survey.id)
        self.assertEqual(saved_survey.title, 'Encrypted Title')
        self.assertEqual(saved_survey.description, 'Encrypted Description')


class SurveyAPITest(APITestCase):
    """Test cases for Survey API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            role='employee'
        )
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='adminpass123',
            role='admin'
        )
        
    def test_create_survey(self):
        """Test creating survey via API"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            'title': 'API Test Survey',
            'description': 'Test survey created via API',
            'visibility': 'PRIVATE'
        }
        
        response = self.client.post('/api/surveys/surveys/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
    
    def test_list_surveys(self):
        """Test listing surveys"""
        Survey.objects.create(
            title='Public Survey',
            creator=self.user,
            visibility='PUBLIC'
        )
        
        response = self.client.get('/api/surveys/surveys/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_survey_permissions(self):
        """Test survey visibility permissions"""
        private_survey = Survey.objects.create(
            title='Private Survey',
            creator=self.admin_user,
            visibility='PRIVATE'
        )
        
        # User should not see private survey they don't own
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'/api/surveys/surveys/{private_survey.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Admin should see their own survey
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f'/api/surveys/surveys/{private_survey.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SurveySubmissionTest(APITestCase):
    """Test cases for survey response submission"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        
        self.survey = Survey.objects.create(
            title='Test Survey',
            creator=self.user,
            visibility='PUBLIC',
            is_active=True
        )
        
        self.question = Question.objects.create(
            survey=self.survey,
            text='What is your name?',
            question_type='text',
            order=1
        )
    
    def test_submit_response(self):
        """Test submitting survey response"""
        data = {
            'answers': [
                {
                    'question_id': str(self.question.id),
                    'answer_text': 'John Doe'
                }
            ]
        }
        
        response = self.client.post(
            f'/api/surveys/surveys/{self.survey.id}/submit/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify response was created
        survey_response = Response.objects.get(survey=self.survey)
        self.assertEqual(survey_response.answers.count(), 1)
    
    def test_submit_to_inactive_survey(self):
        """Test submitting to inactive survey"""
        self.survey.is_active = False
        self.survey.save()
        
        data = {
            'answers': [
                {
                    'question_id': str(self.question.id),
                    'answer_text': 'Test Answer'
                }
            ]
        }
        
        response = self.client.post(
            f'/api/surveys/surveys/{self.survey.id}/submit/',
            data,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class QuestionAnalyticsAPITest(APITestCase):
    """Test cases for question analytics endpoint"""
    
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='admin'
        )
        
        # Create test survey
        self.survey = Survey.objects.create(
            title='Test Survey',
            description='Test Description',
            creator=self.user,
            visibility='PRIVATE',
            is_active=True
        )
        
        # Create test question
        self.question = Question.objects.create(
            survey=self.survey,
            text='What is your favorite color?',
            question_type='single_choice',
            options=json.dumps([
                {'value': 'red', 'label': 'Red'},
                {'value': 'blue', 'label': 'Blue'},
                {'value': 'green', 'label': 'Green'}
            ]),
            is_required=True,
            order=1
        )
        
        # Create test responses
        self.response1 = Response.objects.create(
            survey=self.survey,
            respondent=self.user
        )
        
        self.response2 = Response.objects.create(
            survey=self.survey,
            respondent_email='anonymous@example.com'
        )
        
        # Create test answers
        Answer.objects.create(
            response=self.response1,
            question=self.question,
            answer_text='blue'
        )
        
        Answer.objects.create(
            response=self.response2,
            question=self.question,
            answer_text='red'
        )
        
        # Login user
        self.client.force_authenticate(user=self.user)
    
    def test_get_question_analytics_success(self):
        """Test successful question analytics retrieval"""
        url = f'/api/surveys/surveys/{self.survey.id}/analytics/questions/{self.question.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Question analytics retrieved successfully')
        
        # Check data structure
        data = response.data['data']
        self.assertIn('question', data)
        self.assertIn('summary', data)
        self.assertIn('distributions', data)
        self.assertIn('statistics', data)
        self.assertIn('recent_responses', data)
        self.assertIn('insights', data)
        
        # Check question info
        question_info = data['question']
        self.assertEqual(question_info['id'], str(self.question.id))
        self.assertEqual(question_info['type'], 'single_choice')
        self.assertEqual(question_info['question_text'], 'What is your favorite color?')
        self.assertEqual(question_info['is_required'], True)
        
        # Check summary
        summary = data['summary']
        self.assertEqual(summary['total_responses'], 2)
        self.assertEqual(summary['answered_count'], 2)
        self.assertEqual(summary['skipped_count'], 0)
        self.assertEqual(summary['answer_rate'], 1.0)
        
        # Check distributions
        distributions = data['distributions']
        self.assertIn('by_option', distributions)
        self.assertIn('by_time', distributions)
        self.assertIn('by_auth_status', distributions)
        
        # Check option distribution
        by_option = distributions['by_option']
        self.assertEqual(len(by_option), 3)  # 3 predefined options
        
    def test_get_question_analytics_unauthorized(self):
        """Test unauthorized access to question analytics"""
        # Create another user who is not the creator
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123',
            role='user'
        )
        self.client.force_authenticate(user=other_user)
        
        url = f'/api/surveys/surveys/{self.survey.id}/analytics/questions/{self.question.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_get_question_analytics_not_found(self):
        """Test question analytics for non-existent question"""
        fake_question_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        url = f'/api/surveys/surveys/{self.survey.id}/analytics/questions/{fake_question_id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['message'], 'Question not found in this survey')
    
    def test_get_question_analytics_with_date_filters(self):
        """Test question analytics with date filters"""
        url = f'/api/surveys/surveys/{self.survey.id}/analytics/questions/{self.question.id}/'
        response = self.client.get(url, {
            'start_date': '2024-01-01T00:00:00Z',
            'end_date': '2025-12-31T23:59:59Z',
            'include_demographics': 'true'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
    
    def test_get_rating_question_analytics(self):
        """Test analytics for rating question type"""
        # Create rating question
        rating_question = Question.objects.create(
            survey=self.survey,
            text='Rate our service',
            question_type='rating',
            is_required=True,
            order=2
        )
        
        # Create rating answers
        Answer.objects.create(
            response=self.response1,
            question=rating_question,
            answer_text='5'
        )
        
        Answer.objects.create(
            response=self.response2,
            question=rating_question,
            answer_text='4'
        )
        
        url = f'/api/surveys/surveys/{self.survey.id}/analytics/questions/{rating_question.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        
        # Check rating-specific distributions
        self.assertIn('by_rating', data['distributions'])
        
        # Check rating statistics
        statistics = data['statistics']
        self.assertIn('average', statistics)
        self.assertIn('median', statistics)
        self.assertIn('min', statistics)
        self.assertIn('max', statistics)


class SurveyAccessControlTest(APITestCase):
    """Test cases for survey access control - ensuring draft surveys are not publicly accessible"""
    
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            role='admin'
        )
        
        # Create draft survey
        self.draft_survey = Survey.objects.create(
            title='Draft Survey',
            description='Test Draft Survey',
            creator=self.user,
            visibility='PUBLIC',
            is_active=True,
            status='draft'  # This should not be publicly accessible
        )
        
        # Create submitted survey
        self.submitted_survey = Survey.objects.create(
            title='Submitted Survey',
            description='Test Submitted Survey',
            creator=self.user,
            visibility='PUBLIC',
            is_active=True,
            status='submitted'  # This should be publicly accessible
        )
        
        # Create public access token for both surveys
        self.draft_token = PublicAccessToken.objects.create(
            survey=self.draft_survey,
            token='draft_token_12345',
            created_by=self.user,
            expires_at=timezone.now() + timezone.timedelta(days=30),
            is_active=True
        )
        
        self.submitted_token = PublicAccessToken.objects.create(
            survey=self.submitted_survey,
            token='submitted_token_12345',
            created_by=self.user,
            expires_at=timezone.now() + timezone.timedelta(days=30),
            is_active=True
        )
    
    def test_draft_survey_access_denied_via_public_access_endpoint(self):
        """Test that draft surveys are not accessible via public access endpoint"""
        url = '/api/surveys/surveys/access/'
        response = self.client.get(url, {'token': self.draft_token.token})
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not yet available for public access', response.data['message'])
        self.assertEqual(response.data['data']['reason'], 'survey_not_submitted')
    
    def test_submitted_survey_access_allowed_via_public_access_endpoint(self):
        """Test that submitted surveys are accessible via public access endpoint"""
        url = '/api/surveys/surveys/access/'
        response = self.client.get(url, {'token': self.submitted_token.token})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['data']['has_access'], True)
        self.assertIsNotNone(response.data['data']['survey'])
    
    def test_draft_survey_access_denied_via_survey_access_endpoint(self):
        """Test that draft surveys are not accessible via survey access endpoint"""
        url = f'/api/surveys/surveys/{self.draft_survey.id}/access/'
        response = self.client.get(url, {'token': self.draft_token.token})
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not yet available for public access', response.data['message'])
        self.assertEqual(response.data['data']['reason'], 'survey_not_submitted')
    
    def test_submitted_survey_access_allowed_via_survey_access_endpoint(self):
        """Test that submitted surveys are accessible via survey access endpoint"""
        url = f'/api/surveys/surveys/{self.submitted_survey.id}/access/'
        response = self.client.get(url, {'token': self.submitted_token.token})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['data']['has_access'], True)
    
    def test_draft_survey_access_denied_via_token_surveys_endpoint(self):
        """Test that draft surveys are not accessible via token surveys endpoint"""
        url = '/api/surveys/token/surveys/'
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.draft_token.token}'}
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('not yet available for public access', response.data['message'])
    
    def test_submitted_survey_access_allowed_via_token_surveys_endpoint(self):
        """Test that submitted surveys are accessible via token surveys endpoint"""
        url = '/api/surveys/token/surveys/'
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.submitted_token.token}'}
        response = self.client.get(url, **headers)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')


# Add more test cases as needed...
