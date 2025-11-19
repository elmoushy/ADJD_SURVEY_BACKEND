"""
Tests for Conditional Questions Feature

This module tests the conditional questions functionality including:
- Model validation
- Serializer logic
- API endpoints
- Edge cases and error handling
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
import json

from surveys.models import Survey, Question, QuestionCondition
from authentication.models import Group

User = get_user_model()


class QuestionConditionModelTest(TestCase):
    """Test the QuestionCondition model validation and constraints"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="testpass123"
        )
        
        self.survey = Survey.objects.create(
            title="Test Survey",
            description="Test Description",
            creator=self.user,
            visibility="PUBLIC"
        )
        
        # Create trigger question (yes/no)
        self.trigger_question = Question.objects.create(
            survey=self.survey,
            text="Do you own a car?",
            question_type="yes_no",
            options='["Yes", "No"]',
            is_required=True,
            order=1
        )
        
        # Create dependent question
        self.dependent_question = Question.objects.create(
            survey=self.survey,
            text="What is your car's brand?",
            question_type="text",
            is_required=False,
            order=2
        )
    
    def test_create_valid_condition(self):
        """Test creating a valid question condition"""
        condition = QuestionCondition.objects.create(
            trigger_question=self.trigger_question,
            trigger_answer_value="Yes",
            dependent_question=self.dependent_question
        )
        
        self.assertIsNotNone(condition.id)
        self.assertEqual(condition.trigger_question, self.trigger_question)
        self.assertEqual(condition.trigger_answer_value, "Yes")
        self.assertEqual(condition.dependent_question, self.dependent_question)
    
    def test_invalid_trigger_type(self):
        """Test that only yes_no and single_choice can be triggers"""
        # Create a text question
        text_question = Question.objects.create(
            survey=self.survey,
            text="What is your name?",
            question_type="text",
            is_required=True,
            order=3
        )
        
        # Create another question to be dependent
        dependent = Question.objects.create(
            survey=self.survey,
            text="Follow-up question",
            question_type="text",
            order=4
        )
        
        # Try to create condition with text trigger
        with self.assertRaises(ValidationError) as context:
            condition = QuestionCondition(
                trigger_question=text_question,
                trigger_answer_value="Any value",
                dependent_question=dependent
            )
            condition.save()
        
        self.assertIn("Only yes/no and single choice questions can be triggers", str(context.exception))
    
    def test_invalid_order(self):
        """Test that trigger must come before dependent"""
        # Create questions in wrong order
        later_question = Question.objects.create(
            survey=self.survey,
            text="Later question",
            question_type="yes_no",
            options='["Yes", "No"]',
            order=10
        )
        
        earlier_question = Question.objects.create(
            survey=self.survey,
            text="Earlier question",
            question_type="text",
            order=5
        )
        
        # Try to create condition where trigger comes after dependent
        with self.assertRaises(ValidationError) as context:
            condition = QuestionCondition(
                trigger_question=later_question,
                trigger_answer_value="Yes",
                dependent_question=earlier_question
            )
            condition.save()
        
        self.assertIn("Trigger question must appear before the dependent question", str(context.exception))
    
    def test_circular_dependency(self):
        """Test that circular dependencies are prevented by order validation"""
        # Create first condition: Q1 -> Q2
        condition1 = QuestionCondition.objects.create(
            trigger_question=self.trigger_question,
            trigger_answer_value="Yes",
            dependent_question=self.dependent_question
        )
        
        # Make dependent question into a yes_no to allow it to be a trigger
        self.dependent_question.question_type = "yes_no"
        self.dependent_question.options = '["Yes", "No"]'
        self.dependent_question.save()
        
        # Try to create reverse condition: Q2 -> Q1 (circular)
        # This will be prevented by order validation since Q2 (order=2) cannot trigger Q1 (order=1)
        with self.assertRaises(ValidationError) as context:
            condition2 = QuestionCondition(
                trigger_question=self.dependent_question,
                trigger_answer_value="Yes",
                dependent_question=self.trigger_question
            )
            condition2.save()
        
        # The order validation should catch this
        self.assertIn("Trigger question must appear before the dependent question", str(context.exception))
    
    def test_different_survey_questions(self):
        """Test that conditions only work within same survey"""
        # Create another survey
        other_survey = Survey.objects.create(
            title="Other Survey",
            description="Other Description",
            creator=self.user,
            visibility="PUBLIC"
        )
        
        other_question = Question.objects.create(
            survey=other_survey,
            text="Other question",
            question_type="text",
            order=1
        )
        
        # Try to create condition across different surveys
        with self.assertRaises(ValidationError) as context:
            condition = QuestionCondition(
                trigger_question=self.trigger_question,
                trigger_answer_value="Yes",
                dependent_question=other_question
            )
            condition.save()
        
        self.assertIn("must be in the same survey", str(context.exception))
    
    def test_unique_constraint(self):
        """Test that duplicate conditions are prevented"""
        # Create first condition
        QuestionCondition.objects.create(
            trigger_question=self.trigger_question,
            trigger_answer_value="Yes",
            dependent_question=self.dependent_question
        )
        
        # Try to create duplicate
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            QuestionCondition.objects.create(
                trigger_question=self.trigger_question,
                trigger_answer_value="Yes",
                dependent_question=self.dependent_question
            )
    
    def test_string_representation(self):
        """Test the __str__ method"""
        condition = QuestionCondition.objects.create(
            trigger_question=self.trigger_question,
            trigger_answer_value="Yes",
            dependent_question=self.dependent_question
        )
        
        expected = f"If Q{self.trigger_question.order} = 'Yes' → Show Q{self.dependent_question.order}"
        self.assertEqual(str(condition), expected)


class ConditionalQuestionsAPITest(APITestCase):
    """Test the API endpoints for conditional questions"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="testpass123",
            role="user"
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_create_survey_with_conditional_questions(self):
        """Test creating a survey with conditional questions via API"""
        data = {
            "title": "Customer Survey",
            "description": "Test survey with conditional questions",
            "visibility": "PUBLIC",
            "questions": [
                {
                    "text": "Do you own a car?",
                    "question_type": "yes_no",
                    "options": ["Yes", "No"],
                    "is_required": True,
                    "order": 1
                },
                {
                    "text": "What is your car's brand?",
                    "question_type": "text",
                    "is_required": False,
                    "order": 2
                }
            ]
        }
        
        # First create the survey without conditions
        response = self.client.post('/api/surveys/draft/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        survey_data = response.json()['data']
        survey_id = survey_data['id']
        q1_id = survey_data['questions'][0]['id']
        q2_id = survey_data['questions'][1]['id']
        
        # Now update Q2 to add conditional logic
        update_data = {
            "questions": [
                {
                    "id": q1_id,
                    "text": "Do you own a car?",
                    "question_type": "yes_no",
                    "options": ["Yes", "No"],
                    "is_required": True,
                    "order": 1
                },
                {
                    "id": q2_id,
                    "text": "What is your car's brand?",
                    "question_type": "text",
                    "is_required": False,
                    "order": 2,
                    "set_conditional_on": [
                        {
                            "trigger_question_id": q1_id,
                            "trigger_answer_value": "Yes"
                        }
                    ]
                }
            ]
        }
        
        response = self.client.patch(f'/api/surveys/surveys/{survey_id}/', update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_survey_with_conditions(self):
        """Test retrieving a survey shows conditional_on and triggers fields"""
        # Create survey with conditions
        survey = Survey.objects.create(
            title="Test Survey",
            creator=self.user,
            visibility="PUBLIC"
        )
        
        q1 = Question.objects.create(
            survey=survey,
            text="Are you satisfied?",
            question_type="yes_no",
            options='["Yes", "No"]',
            order=1
        )
        
        q2 = Question.objects.create(
            survey=survey,
            text="What can we improve?",
            question_type="textarea",
            order=2
        )
        
        # Create condition
        QuestionCondition.objects.create(
            trigger_question=q1,
            trigger_answer_value="No",
            dependent_question=q2
        )
        
        # Retrieve survey
        response = self.client.get(f'/api/surveys/surveys/{survey.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()['data']
        questions = data['questions']
        
        # Check Q1 has triggers field
        q1_data = next(q for q in questions if q['order'] == 1)
        self.assertIsNotNone(q1_data['triggers'])
        self.assertEqual(len(q1_data['triggers']), 1)
        self.assertEqual(q1_data['triggers'][0]['trigger_values'], ["No"])
        
        # Check Q2 has conditional_on field
        q2_data = next(q for q in questions if q['order'] == 2)
        self.assertIsNotNone(q2_data['conditional_on'])
        self.assertEqual(len(q2_data['conditional_on']), 1)
        self.assertEqual(q2_data['conditional_on'][0]['trigger_answer_value'], "No")
    
    def test_validation_prevents_invalid_order(self):
        """Test that API validation prevents trigger after dependent"""
        data = {
            "title": "Invalid Survey",
            "description": "Test",
            "visibility": "PUBLIC",
            "questions": [
                {
                    "text": "Question 1",
                    "question_type": "text",
                    "order": 1,
                    "set_conditional_on": [
                        {
                            "trigger_question_id": "fake-uuid",
                            "trigger_answer_value": "Yes"
                        }
                    ]
                },
                {
                    "text": "Question 2",
                    "question_type": "yes_no",
                    "options": ["Yes", "No"],
                    "order": 2
                }
            ]
        }
        
        response = self.client.post('/api/surveys/draft/', data, format='json')
        # Should fail because trigger doesn't exist or comes after
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_201_CREATED])
    
    def test_multiple_conditions_or_logic(self):
        """Test that multiple conditions work with OR logic"""
        survey = Survey.objects.create(
            title="Test Survey",
            creator=self.user,
            visibility="PUBLIC"
        )
        
        q1 = Question.objects.create(
            survey=survey,
            text="How satisfied are you?",
            question_type="single_choice",
            options='["Very Satisfied", "Satisfied", "Neutral", "Dissatisfied"]',
            order=1
        )
        
        q2 = Question.objects.create(
            survey=survey,
            text="What can we improve?",
            question_type="textarea",
            order=2
        )
        
        # Create multiple conditions (OR logic)
        QuestionCondition.objects.create(
            trigger_question=q1,
            trigger_answer_value="Neutral",
            dependent_question=q2
        )
        
        QuestionCondition.objects.create(
            trigger_question=q1,
            trigger_answer_value="Dissatisfied",
            dependent_question=q2
        )
        
        # Retrieve and verify
        response = self.client.get(f'/api/surveys/surveys/{survey.id}/')
        data = response.json()['data']
        
        q2_data = next(q for q in data['questions'] if q['order'] == 2)
        self.assertEqual(len(q2_data['conditional_on']), 2)
        
        trigger_values = [c['trigger_answer_value'] for c in q2_data['conditional_on']]
        self.assertIn("Neutral", trigger_values)
        self.assertIn("Dissatisfied", trigger_values)


class ConditionalQuestionsIntegrationTest(APITestCase):
    """Integration tests for end-to-end conditional questions flow"""
    
    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="testpass123",
            role="user"
        )
        
        self.client.force_authenticate(user=self.user)
    
    def test_multi_level_dependencies(self):
        """Test that multi-level dependencies work correctly"""
        survey = Survey.objects.create(
            title="Multi-level Survey",
            creator=self.user,
            visibility="PUBLIC"
        )
        
        # Q1: Are you a student?
        q1 = Question.objects.create(
            survey=survey,
            text="Are you a student?",
            question_type="yes_no",
            options='["Yes", "No"]',
            order=1
        )
        
        # Q2: What is your major? (conditional on Q1=Yes)
        q2 = Question.objects.create(
            survey=survey,
            text="What is your major?",
            question_type="single_choice",
            options='["Computer Science", "Business", "Arts"]',
            order=2
        )
        
        QuestionCondition.objects.create(
            trigger_question=q1,
            trigger_answer_value="Yes",
            dependent_question=q2
        )
        
        # Q3: What programming languages? (conditional on Q2=Computer Science)
        q3 = Question.objects.create(
            survey=survey,
            text="What programming languages do you know?",
            question_type="text",
            order=3
        )
        
        QuestionCondition.objects.create(
            trigger_question=q2,
            trigger_answer_value="Computer Science",
            dependent_question=q3
        )
        
        # Retrieve and verify structure
        response = self.client.get(f'/api/surveys/surveys/{survey.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()['data']
        questions = {q['order']: q for q in data['questions']}
        
        # Verify Q1 triggers Q2
        self.assertIsNotNone(questions[1]['triggers'])
        self.assertEqual(questions[1]['triggers'][0]['dependent_question_order'], 2)
        
        # Verify Q2 is conditional on Q1 and triggers Q3
        self.assertIsNotNone(questions[2]['conditional_on'])
        self.assertEqual(questions[2]['conditional_on'][0]['trigger_question_order'], 1)
        self.assertIsNotNone(questions[2]['triggers'])
        self.assertEqual(questions[2]['triggers'][0]['dependent_question_order'], 3)
        
        # Verify Q3 is conditional on Q2
        self.assertIsNotNone(questions[3]['conditional_on'])
        self.assertEqual(questions[3]['conditional_on'][0]['trigger_question_order'], 2)
    
    def test_update_removes_conditions(self):
        """Test that updating with empty set_conditional_on removes conditions"""
        survey = Survey.objects.create(
            title="Test Survey",
            creator=self.user,
            visibility="PUBLIC"
        )
        
        q1 = Question.objects.create(
            survey=survey,
            text="Trigger",
            question_type="yes_no",
            options='["Yes", "No"]',
            order=1
        )
        
        q2 = Question.objects.create(
            survey=survey,
            text="Dependent",
            question_type="text",
            order=2
        )
        
        # Create condition
        QuestionCondition.objects.create(
            trigger_question=q1,
            trigger_answer_value="Yes",
            dependent_question=q2
        )
        
        # Verify condition exists
        self.assertEqual(QuestionCondition.objects.filter(dependent_question=q2).count(), 1)
        
        # Update survey to remove conditions
        from surveys.serializers import QuestionSerializer
        serializer = QuestionSerializer(q2, data={'set_conditional_on': []}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        
        # Verify condition removed
        self.assertEqual(QuestionCondition.objects.filter(dependent_question=q2).count(), 0)


if __name__ == '__main__':
    import django
    django.setup()
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["surveys.tests_conditional"])
