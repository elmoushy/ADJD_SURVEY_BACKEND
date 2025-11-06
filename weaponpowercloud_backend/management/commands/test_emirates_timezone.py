"""
Django Management Command: Test Emirates Timezone

This command helps verify that your Emirates timezone configuration
is working correctly across your Django application.

Usage:
    python manage.py test_emirates_timezone
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
import pytz


class Command(BaseCommand):
    help = 'Test Emirates timezone configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed timezone information',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('=== Emirates Timezone Configuration Test ===')
        )
        
        # Test 1: Django settings
        from django.conf import settings
        self.stdout.write(f"\n1. Django Settings:")
        self.stdout.write(f"   TIME_ZONE: {settings.TIME_ZONE}")
        self.stdout.write(f"   USE_TZ: {settings.USE_TZ}")
        
        # Test 2: Current timezone
        self.stdout.write(f"\n2. Current Active Timezone:")
        current_tz = timezone.get_current_timezone()
        self.stdout.write(f"   Active timezone: {current_tz}")
        
        # Test 3: Time comparisons
        self.stdout.write(f"\n3. Time Comparisons:")
        utc_now = timezone.now()
        local_now = timezone.localtime(timezone.now())
        
        self.stdout.write(f"   UTC time: {utc_now}")
        self.stdout.write(f"   Local time: {local_now}")
        self.stdout.write(f"   Offset: {local_now.utcoffset()}")
        
        # Test 4: Timezone activation
        self.stdout.write(f"\n4. Manual Timezone Activation Test:")
        timezone.activate('Asia/Dubai')
        emirates_local = timezone.localtime(timezone.now())
        self.stdout.write(f"   After activating Asia/Dubai: {emirates_local}")
        
        # Test 5: Other timezone comparison (if verbose)
        if options['verbose']:
            self.stdout.write(f"\n5. Comparison with Other Timezones:")
            
            timezones_to_test = [
                'UTC',
                'US/Eastern',
                'Europe/London',
                'Asia/Tokyo',
            ]
            
            base_time = timezone.now()
            for tz_name in timezones_to_test:
                tz = pytz.timezone(tz_name)
                converted_time = base_time.astimezone(tz)
                self.stdout.write(f"   {tz_name}: {converted_time}")
        
        # Test 6: Database timezone handling
        self.stdout.write(f"\n6. Database Timezone Test:")
        try:
            from authentication.models import User
            # Try to get a user and check timestamp timezone
            user = User.objects.first()
            if user:
                if hasattr(user, 'date_joined'):
                    local_joined = timezone.localtime(user.date_joined)
                    self.stdout.write(f"   Sample user date_joined (local): {local_joined}")
                else:
                    self.stdout.write("   No date_joined field found")
            else:
                self.stdout.write("   No users found in database")
        except Exception as e:
            self.stdout.write(f"   Database test failed: {e}")
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ Emirates timezone test completed!')
        )
        
        # Recommendations
        self.stdout.write(f"\n📋 Recommendations:")
        self.stdout.write("   - All times should show +04:00 offset (Emirates Standard Time)")
        self.stdout.write("   - Verify API responses use Emirates timezone")
        self.stdout.write("   - Check that scheduled tasks use correct timezone")
        
        if settings.TIME_ZONE == 'Asia/Dubai':
            self.stdout.write(
                self.style.SUCCESS("   ✅ TIME_ZONE correctly set to Asia/Dubai")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"   ❌ TIME_ZONE is {settings.TIME_ZONE}, should be Asia/Dubai")
            )
