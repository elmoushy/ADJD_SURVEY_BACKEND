"""
Django signals for automatic notification triggering.

This module contains signal handlers that automatically create and send
notifications when certain survey events occur, such as surveys being
shared, published, or responses being completed.
"""

import logging
from django.db.models.signals import post_save, m2m_changed, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Survey, Response
from notifications.services import NotificationService, SurveyNotificationService
from notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()

# Track survey states for change detection
_survey_old_states = {}


@receiver(pre_save, sender=Survey)
def track_survey_changes(sender, instance, **kwargs):
    """
    Track survey changes before saving to detect status/activation changes.
    
    This signal captures the old state of the survey so we can detect
    changes after the save operation.
    """
    if instance.pk:  # Only for existing surveys
        try:
            old_survey = Survey.objects.get(pk=instance.pk)
            _survey_old_states[instance.pk] = {
                'is_active': old_survey.is_active,
                'status': old_survey.status,
                'visibility': old_survey.visibility
            }
            logger.debug(f"Tracked old state for survey {instance.pk}: {_survey_old_states[instance.pk]}")
        except Survey.DoesNotExist:
            pass


@receiver(m2m_changed, sender=Survey.shared_with.through)
def survey_shared_notification(sender, instance, action, pk_set, **kwargs):
    """
    Send notifications when a survey is shared with users.
    
    This signal is triggered when users are added to a survey's shared_with field.
    """
    if action == 'post_add' and pk_set:
        survey = instance
        
        # Only send notifications for submitted surveys
        if survey.status != 'submitted':
            logger.debug(f"Skipping notification for draft survey {survey.id}")
            return
        
        # Get the newly added users
        new_users = User.objects.filter(pk__in=pk_set)
        
        # Create survey URL
        survey_url = f"/surveys/{survey.id}/"
        
        # Send notification to each newly shared user
        for user in new_users:
            try:
                NotificationService.create_survey_assigned_notification(
                    recipient=user,
                    survey_title=survey.title,
                    sender=survey.creator,
                    survey_id=str(survey.id),
                    survey_url=survey_url
                )
                logger.info(
                    f"Sent survey assigned notification to {user.email} "
                    f"for survey {survey.id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send survey assigned notification to {user.email} "
                    f"for survey {survey.id}: {str(e)}"
                )


@receiver(m2m_changed, sender=Survey.shared_with_groups.through)
def survey_shared_with_groups_notification(sender, instance, action, pk_set, **kwargs):
    """
    Send notifications when a survey is shared with groups.
    
    This signal is triggered when groups are added to a survey's shared_with_groups field.
    """
    if action == 'post_add' and pk_set:
        survey = instance
        
        # Only send notifications for submitted surveys
        if survey.status != 'submitted':
            logger.debug(f"Skipping group notification for draft survey {survey.id}")
            return
        
        # Get the newly added groups and their users
        try:
            from authentication.models import Group
            new_groups = Group.objects.filter(pk__in=pk_set)
            
            # Create survey URL
            survey_url = f"/surveys/{survey.id}/"
            
            # Send notification to each user in the newly shared groups
            for group in new_groups:
                group_users = group.users.all()
                
                for user in group_users:
                    try:
                        NotificationService.create_survey_assigned_notification(
                            recipient=user,
                            survey_title=survey.title,
                            sender=survey.creator,
                            survey_id=str(survey.id),
                            survey_url=survey_url
                        )
                        logger.info(
                            f"Sent survey assigned notification to {user.email} "
                            f"for survey {survey.id} (via group {group.name})"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send survey assigned notification to {user.email} "
                            f"for survey {survey.id} via group {group.name}: {str(e)}"
                        )
                        
        except ImportError:
            logger.error("Could not import Group model from authentication app")
        except Exception as e:
            logger.error(f"Error processing group notifications for survey {survey.id}: {str(e)}")


@receiver(post_save, sender=Survey)
def survey_status_change_notification(sender, instance, created, **kwargs):
    """
    Send notifications when a survey is created, published, or status changes.
    
    This signal is triggered when a survey is saved, and handles:
    - New surveys being published (draft -> submitted)
    - Surveys being activated/deactivated
    - Survey visibility changes
    """
    try:
        survey = instance
        
        if created:
            logger.debug(f"Survey {survey.id} was created, skipping notifications until submitted")
            return
        
        # Get old state if available
        old_state = _survey_old_states.get(survey.pk, {})
        old_status = old_state.get('status')
        old_is_active = old_state.get('is_active')
        old_visibility = old_state.get('visibility')
        
        # Clean up the old state to prevent memory leaks
        if survey.pk in _survey_old_states:
            del _survey_old_states[survey.pk]
        
        # Check for survey being published (draft -> submitted)
        if old_status == 'draft' and survey.status == 'submitted' and survey.is_active:
            logger.info(f"Survey {survey.id} was published, sending availability notifications")
            try:
                SurveyNotificationService.notify_users_of_new_survey(survey)
            except Exception as e:
                logger.error(f"Failed to send publication notifications for survey {survey.id}: {e}")
        
        # Check for survey being deactivated
        elif old_is_active == True and survey.is_active == False:
            logger.info(f"Survey {survey.id} was deactivated, sending deactivation notifications")
            try:
                # We need to get the user who made this change - this is tricky from a signal
                # For now, we'll use the survey creator as the deactivator
                # In a real implementation, you might want to pass this through the request context
                SurveyNotificationService.notify_users_of_survey_deactivation(
                    survey, 
                    survey.creator  # Using creator as fallback deactivator
                )
            except Exception as e:
                logger.error(f"Failed to send deactivation notifications for survey {survey.id}: {e}")
        
        # Check for survey being reactivated after publication
        elif old_is_active == False and survey.is_active == True and survey.status == 'submitted':
            logger.info(f"Survey {survey.id} was reactivated, sending availability notifications")
            try:
                SurveyNotificationService.notify_users_of_new_survey(survey)
            except Exception as e:
                logger.error(f"Failed to send reactivation notifications for survey {survey.id}: {e}")
        
        # Check for visibility changes
        elif old_visibility and old_visibility != survey.visibility and survey.status == 'submitted' and survey.is_active:
            logger.info(f"Survey {survey.id} visibility changed from {old_visibility} to {survey.visibility}")
            try:
                # Send notifications to newly eligible users
                SurveyNotificationService.notify_users_of_new_survey(survey)
            except Exception as e:
                logger.error(f"Failed to send visibility change notifications for survey {survey.id}: {e}")
                
    except Exception as e:
        logger.error(f"Error processing survey status change notification for survey {instance.pk}: {e}")


@receiver(post_save, sender=Response)
def survey_response_completed_notification(sender, instance, created, **kwargs):
    """
    Send notification to survey creator when a response is completed.
    
    This signal is triggered when a new response is created.
    """
    if created and instance.is_complete:
        response = instance
        survey = response.survey
        
        # Get respondent information
        if response.respondent:
            respondent_name = (
                response.respondent.full_name or 
                response.respondent.username or 
                response.respondent.email
            )
        else:
            # Anonymous respondent
            respondent_name = (
                response.respondent_email or 
                response.respondent_phone or 
                "Anonymous User"
            )
        
        # Create survey results URL
        survey_url = f"/surveys/{survey.id}/results/"
        
        # Send notification to survey creator
        try:
            # Only send notification if the creator still exists
            if survey.creator:
                NotificationService.create_survey_completed_notification(
                    recipient=survey.creator,
                    survey_title=survey.title,
                    respondent_name=respondent_name,
                    survey_id=str(survey.id),
                    survey_url=survey_url
                )
                logger.info(
                    f"Sent survey completed notification to {survey.creator.email} "
                    f"for response {response.id} to survey {survey.id}"
                )
            else:
                logger.info(
                    f"Skipped survey completed notification for deleted user "
                    f"for response {response.id} to survey {survey.id}"
                )
        except Exception as e:
            creator_email = survey.creator.email if survey.creator else 'Deleted User'
            logger.error(
                f"Failed to send survey completed notification to {creator_email} "
                f"for response {response.id} to survey {survey.id}: {str(e)}"
            )
        
        # Also notify users who are shared with the survey (if they want completion notifications)
        try:
            # Get users who have completion notifications enabled for this survey
            shared_users = survey.shared_with.all()
            
            for shared_user in shared_users:
                # Check user preferences - only send if they want survey completion notifications
                try:
                    from notifications.models import NotificationPreference
                    prefs = NotificationPreference.objects.get(user=shared_user)
                    
                    # Only send if user wants survey completed notifications
                    if prefs.survey_completed:
                        NotificationService.create_survey_completed_notification(
                            recipient=shared_user,
                            survey_title=survey.title,
                            respondent_name=respondent_name,
                            survey_id=str(survey.id),
                            survey_url=survey_url
                        )
                        logger.info(
                            f"Sent survey completed notification to shared user {shared_user.email} "
                            f"for response {response.id} to survey {survey.id}"
                        )
                except NotificationPreference.DoesNotExist:
                    # User has no preferences, use default (send notification)
                    NotificationService.create_survey_completed_notification(
                        recipient=shared_user,
                        survey_title=survey.title,
                        respondent_name=respondent_name,
                        survey_id=str(survey.id),
                        survey_url=survey_url
                    )
                    logger.info(
                        f"Sent survey completed notification to shared user {shared_user.email} "
                        f"for response {response.id} to survey {survey.id} (default preferences)"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send survey completed notification to shared user {shared_user.email} "
                        f"for response {response.id} to survey {survey.id}: {str(e)}"
                    )
                    
        except Exception as e:
            logger.error(f"Error processing shared user notifications for survey {survey.id}: {str(e)}")


def send_survey_deadline_reminder(survey, days_remaining):
    """
    Send deadline reminder notifications for surveys.
    
    This function can be called from a periodic task to remind users
    about upcoming survey deadlines.
    """
    if survey.end_date and survey.status == 'submitted':
        # Create reminder message
        survey_url = f"/surveys/{survey.id}/"
        
        # Get all users who have access to this survey
        recipients = set()
        
        # Add shared users
        recipients.update(survey.shared_with.all())
        
        # Add group users
        try:
            from authentication.models import Group
            for group in survey.shared_with_groups.all():
                recipients.update(group.users.all())
        except ImportError:
            pass
        
        # Send reminder to each recipient
        for user in recipients:
            try:
                # Check user preferences - only send if they want deadline reminders
                try:
                    from notifications.models import NotificationPreference
                    prefs = NotificationPreference.objects.get(user=user)
                    
                    # Only send if user wants deadline reminders
                    if not prefs.survey_assigned:  # Using survey_assigned as proxy for deadline reminders
                        continue
                        
                except NotificationPreference.DoesNotExist:
                    # User has no preferences, use default (send notification)
                    pass
                
                # Create deadline reminder notification
                if days_remaining == 1:
                    title_en = f"Survey Deadline Tomorrow: {survey.title}"
                    title_ar = f"موعد انتهاء الاستبيان غداً: {survey.title}"
                    message_en = f"Reminder: The survey '{survey.title}' closes tomorrow. Please complete it if you haven't already."
                    message_ar = f"تذكير: ينتهي الاستبيان '{survey.title}' غداً. يرجى إكماله إذا لم تفعل ذلك بعد."
                else:
                    title_en = f"Survey Deadline in {days_remaining} Days: {survey.title}"
                    title_ar = f"موعد انتهاء الاستبيان خلال {days_remaining} أيام: {survey.title}"
                    message_en = f"Reminder: The survey '{survey.title}' closes in {days_remaining} days. Please complete it if you haven't already."
                    message_ar = f"تذكير: ينتهي الاستبيان '{survey.title}' خلال {days_remaining} أيام. يرجى إكماله إذا لم تفعل ذلك بعد."
                
                NotificationService.create_admin_message_notification(
                    recipient=user,
                    title={'en': title_en, 'ar': title_ar},
                    message={'en': message_en, 'ar': message_ar},
                    priority=Notification.PRIORITY_HIGH,
                    action_url=survey_url
                )
                
                logger.info(
                    f"Sent deadline reminder notification to {user.email} "
                    f"for survey {survey.id} ({days_remaining} days remaining)"
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to send deadline reminder to {user.email} "
                    f"for survey {survey.id}: {str(e)}"
                )
