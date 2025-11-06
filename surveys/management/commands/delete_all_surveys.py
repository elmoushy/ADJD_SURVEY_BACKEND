"""
Django management command to force delete all surveys

This command completely removes ALL surveys and their related data from the database.

Usage:
    python manage.py delete_all_surveys [--dry-run] [--confirm]
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from surveys.models import Survey, Question, Response, Answer, PublicAccessToken


class Command(BaseCommand):
    help = 'Force delete all surveys and related data (IRREVERSIBLE)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip interactive confirmation (use with caution)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING('Survey Force Deletion Tool')
        )
        self.stdout.write('=' * 40)
        
        # Get current statistics
        initial_stats = self.get_survey_stats()
        self.print_stats(initial_stats, "Current Database Statistics")
        
        # Check if there's anything to delete
        if initial_stats['surveys'] == 0:
            self.stdout.write(
                self.style.SUCCESS('\n✅ No surveys found in the database.')
            )
            return
        
        # Confirmation (skip if dry-run or --confirm flag)
        if not options['dry_run'] and not options['confirm']:
            if not self.confirm_deletion():
                self.stdout.write(
                    self.style.ERROR('\n❌ Deletion cancelled by user.')
                )
                return
        
        # Perform deletion
        try:
            deleted_stats = self.delete_all_surveys(dry_run=options['dry_run'])
            
            # Show what was deleted
            action = "Would be deleted" if options['dry_run'] else "Deleted"
            self.stdout.write(f"\n{action} Statistics:")
            self.stdout.write('=' * 40)
            self.stdout.write(f"Surveys: {deleted_stats['surveys']}")
            self.stdout.write(f"Questions: {deleted_stats['questions']}")
            self.stdout.write(f"Responses: {deleted_stats['responses']}")
            self.stdout.write(f"Answers: {deleted_stats['answers']}")
            self.stdout.write(f"Public Access Tokens: {deleted_stats['public_tokens']}")
            self.stdout.write(f"Sharing Relationships: {deleted_stats['shared_relationships']}")
            self.stdout.write('=' * 40)
            
            if not options['dry_run']:
                # Verify deletion
                final_stats = self.get_survey_stats()
                self.print_stats(final_stats, "Final Database Statistics")
                
                if final_stats['surveys'] == 0:
                    self.stdout.write(
                        self.style.SUCCESS('\n✅ All surveys successfully deleted!')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n⚠️  Warning: {final_stats["surveys"]} surveys still remain'
                        )
                    )
            
        except Exception as e:
            raise CommandError(f'Script failed with error: {str(e)}')
    
    def get_survey_stats(self):
        """Get current survey statistics"""
        stats = {
            'surveys': Survey.objects.count(),
            'surveys_active': Survey.objects.filter(deleted_at__isnull=True).count(),
            'surveys_soft_deleted': Survey.objects.filter(deleted_at__isnull=False).count(),
            'questions': Question.objects.count(),
            'responses': Response.objects.count(),
            'answers': Answer.objects.count(),
            'public_tokens': PublicAccessToken.objects.count(),
        }
        return stats
    
    def print_stats(self, stats, title="Current Statistics"):
        """Print survey statistics in a formatted way"""
        self.stdout.write(f"\n{title}:")
        self.stdout.write('=' * 40)
        self.stdout.write(f"Total Surveys: {stats['surveys']}")
        self.stdout.write(f"  - Active: {stats['surveys_active']}")
        self.stdout.write(f"  - Soft Deleted: {stats['surveys_soft_deleted']}")
        self.stdout.write(f"Questions: {stats['questions']}")
        self.stdout.write(f"Responses: {stats['responses']}")
        self.stdout.write(f"Answers: {stats['answers']}")
        self.stdout.write(f"Public Access Tokens: {stats['public_tokens']}")
        self.stdout.write('=' * 40)
    
    def confirm_deletion(self):
        """Interactive confirmation for deletion"""
        self.stdout.write('\n' + '!' * 60)
        self.stdout.write(
            self.style.ERROR('WARNING: THIS WILL PERMANENTLY DELETE ALL SURVEY DATA!')
        )
        self.stdout.write('!' * 60)
        self.stdout.write('\nThis action will:')
        self.stdout.write('- Delete ALL surveys (including soft-deleted ones)')
        self.stdout.write('- Delete ALL questions')
        self.stdout.write('- Delete ALL responses')
        self.stdout.write('- Delete ALL answers')
        self.stdout.write('- Delete ALL public access tokens')
        self.stdout.write('- Remove ALL sharing relationships')
        self.stdout.write('\nThis action is IRREVERSIBLE!')
        
        confirmation = input("\nType 'DELETE ALL SURVEYS' to confirm: ")
        return confirmation == 'DELETE ALL SURVEYS'
    
    def delete_all_surveys(self, dry_run=False):
        """
        Force delete all surveys and related data
        
        Args:
            dry_run (bool): If True, only show what would be deleted without deleting
            
        Returns:
            dict: Statistics of what was deleted
        """
        self.stdout.write(
            f"\n{'DRY RUN - ' if dry_run else ''}Starting survey deletion process..."
        )
        
        deleted_stats = {
            'surveys': 0,
            'questions': 0,
            'responses': 0,
            'answers': 0,
            'public_tokens': 0,
            'shared_relationships': 0,
        }
        
        try:
            with transaction.atomic():
                # Get counts before deletion
                surveys = Survey.objects.all()
                questions = Question.objects.all()
                responses = Response.objects.all()
                answers = Answer.objects.all()
                public_tokens = PublicAccessToken.objects.all()
                
                deleted_stats['surveys'] = surveys.count()
                deleted_stats['questions'] = questions.count()
                deleted_stats['responses'] = responses.count()
                deleted_stats['answers'] = answers.count()
                deleted_stats['public_tokens'] = public_tokens.count()
                
                # Count shared relationships
                shared_count = 0
                for survey in surveys:
                    shared_count += survey.shared_with.count()
                    shared_count += survey.shared_with_groups.count()
                deleted_stats['shared_relationships'] = shared_count
                
                if not dry_run:
                    self.stdout.write('\nDeleting survey data...')
                    
                    # Delete in proper order to avoid foreign key constraints
                    self.stdout.write('- Deleting answers...')
                    answers.delete()
                    
                    self.stdout.write('- Deleting responses...')
                    responses.delete()
                    
                    self.stdout.write('- Deleting public access tokens...')
                    public_tokens.delete()
                    
                    self.stdout.write('- Clearing sharing relationships...')
                    for survey in surveys:
                        survey.shared_with.clear()
                        survey.shared_with_groups.clear()
                    
                    self.stdout.write('- Deleting questions...')
                    questions.delete()
                    
                    self.stdout.write('- Deleting surveys...')
                    surveys.delete()
                    
                    self.stdout.write(
                        self.style.SUCCESS('✅ All survey data deleted successfully!')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING('\n🔍 DRY RUN - No actual deletion performed')
                    )
                    
        except Exception as e:
            if not dry_run:
                self.stdout.write(
                    self.style.ERROR('Transaction rolled back - no data was deleted')
                )
            raise
        
        return deleted_stats
