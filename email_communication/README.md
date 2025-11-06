# Email Communication System - Quick Start Guide

## Overview
The Email Communication System allows users to send templated emails to cost centers with support for announcement broadcasts and specific cost center targeting. Built with Django REST Framework and follows the project's Oracle database compatibility patterns.

## Features Implemented

✅ **Cost Center Management**
- Create and manage cost centers with associated users
- Bilingual support (English/Arabic)
- Manager and common CC email configuration

✅ **Email Templates**
- Pre-defined templates that users can edit before sending
- Category-based organization
- Rich HTML content support
- Active/inactive status management

✅ **Draft Management**
- Save emails as drafts before sending
- Edit and update drafts
- Send from saved drafts

✅ **Email Sending**
- Send to all cost centers (Announcement)
- Send to specific cost centers
- Automatic recipient tracking
- CC email support

✅ **Mailbox System**
- **Inbox**: Received emails with read/unread status
- **Outbox**: Sent emails history
- **Transactions Log**: Complete email activity audit trail
- Per-user read, star, and archive status

✅ **Oracle + SQL Server + SQLite Compatibility**
- Hash-based indexing for encrypted fields
- Database-agnostic managers
- Tested migration path

## Database Tables Created

1. **email_costcenter** - Cost centers with users
2. **email_template** - Email templates
3. **email_draft** - Saved drafts
4. **email_log** - Email send/receive logs
5. **email_recipient_view** - Per-recipient inbox tracking

## API Endpoints Available

### Cost Centers
```
GET    /api/email/cost-centers/          - List cost centers
POST   /api/email/cost-centers/          - Create cost center
GET    /api/email/cost-centers/{id}/     - Get cost center detail
PUT    /api/email/cost-centers/{id}/     - Update cost center
DELETE /api/email/cost-centers/{id}/     - Delete cost center
GET    /api/email/cost-centers/{id}/users/ - Get cost center users
```

### Templates
```
GET    /api/email/templates/             - List templates
POST   /api/email/templates/             - Create template
GET    /api/email/templates/{id}/        - Get template detail
PUT    /api/email/templates/{id}/        - Update template
DELETE /api/email/templates/{id}/        - Delete template
```

### Drafts
```
GET    /api/email/drafts/                - List user's drafts
POST   /api/email/drafts/                - Create draft
GET    /api/email/drafts/{id}/           - Get draft detail
PUT    /api/email/drafts/{id}/           - Update draft
DELETE /api/email/drafts/{id}/           - Delete draft (soft delete)
```

### Email Operations
```
POST   /api/email/send/                  - Send email
POST   /api/email/send-draft/{id}/       - Send from draft
```

### Mailbox
```
GET    /api/email/inbox/                 - User's inbox
GET    /api/email/inbox/{id}/            - Get inbox email (marks as read)
POST   /api/email/inbox/{id}/mark-read/  - Mark email as read
POST   /api/email/inbox/{id}/star/       - Toggle star status
POST   /api/email/inbox/{id}/archive/    - Toggle archive status
GET    /api/email/outbox/                - User's sent emails
GET    /api/email/transactions/          - Email transactions log
```

## Quick Test Commands

### 1. Create a Cost Center
```powershell
.\.venv\Scripts\Activate.ps1; python manage.py shell
```

```python
from email_communication.models import CostCenter
from authentication.models import User

# Get a user to assign as created_by
admin = User.objects.filter(role='super_admin').first()

# Create cost center
cc = CostCenter.objects.create(
    cost_center_code='CC-TEST-001',
    cost_center_name='Test Cost Center',
    cost_center_name_ar='مركز التكلفة التجريبي',
    description='Test cost center for email system',
    is_active=True,
    manager_email='manager@example.com',
    created_by=admin
)

# Add users to cost center
users = User.objects.filter(role='user')[:3]
cc.users.set(users)
cc.save()

print(f"Created cost center: {cc}")
print(f"Users: {cc.get_user_emails()}")
print(f"CC Emails: {cc.get_cc_emails()}")
```

### 2. Create an Email Template
```python
from email_communication.models import EmailTemplate

template = EmailTemplate.objects.create(
    name='Meeting Announcement',
    name_ar='إعلان اجتماع',
    subject='Team Meeting - {date}',
    subject_ar='اجتماع الفريق - {date}',
    body_html='<h1>Meeting Notice</h1><p>Dear Team,</p><p>Please join us for...</p>',
    body_html_ar='<h1>إشعار اجتماع</h1><p>عزيزي الفريق،</p><p>يرجى الانضمام إلينا...</p>',
    is_active=True,
    category='meeting',
    created_by=admin
)

print(f"Created template: {template}")
```

### 3. Test Email Sending (Console Backend in DEBUG mode)
```python
from email_communication.services import EmailService

# Send to specific cost center
result = EmailService.send_email(
    user=admin,
    send_type='SPECIFIC',
    subject='Test Email - Meeting Tomorrow',
    body_html='<h1>Meeting</h1><p>This is a test email.</p>',
    cost_center_ids=[cc.id],
    template_id=template.id
)

print(f"Send result: {result}")

# Check email logs
from email_communication.models import EmailLog
logs = EmailLog.objects.all()
for log in logs:
    print(f"Log: {log.email_type} - {log.subject} - {log.email_status}")

# Check recipient views
from email_communication.models import EmailRecipientView
views = EmailRecipientView.objects.all()
for view in views:
    print(f"Recipient: {view.recipient_user.email} - Read: {view.is_read}")
```

### 4. Test Inbox API (via curl or browser)
```powershell
# Get inbox (requires authentication token)
curl -X GET http://localhost:8000/api/email/inbox/ -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Get templates
curl -X GET http://localhost:8000/api/email/templates/?is_active=true -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Get cost centers
curl -X GET http://localhost:8000/api/email/cost-centers/ -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Email Configuration

### Development (Console Backend)
Emails are printed to console for testing:
```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### Production (SMTP Backend)
Add to `.env` file:
```env
# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@lightidea.org
```

## Django Admin Access

1. Access admin: http://localhost:8000/admin/
2. Navigate to "EMAIL COMMUNICATION SYSTEM" section
3. Manage:
   - Cost Centers (add users, configure emails)
   - Email Templates (create/edit templates)
   - Email Drafts (view user drafts)
   - Email Logs (view all sent emails)
   - Email Recipient Views (view inbox tracking)

## Permissions

- **Can Send Email**: All authenticated users (customizable)
- **Can Manage Cost Centers**: Admins and Super Admins only
- **Can Create Templates**: Admins and Super Admins only
- **Draft Owner**: Only draft owner can edit/delete/send their drafts
- **Inbox Access**: Users see only emails they received

## Testing Workflow

1. **Create Cost Centers** (Admin panel or API)
2. **Add Users to Cost Centers** (Admin panel)
3. **Create Email Templates** (Admin panel or API)
4. **Compose Email** (Frontend):
   - Select template (optional)
   - Edit subject and body
   - Choose send type (Announcement/Specific)
   - Select cost centers (if Specific)
5. **Send or Save as Draft**
6. **Recipients Check Inbox** (API)
7. **View Transactions Log** (Admin)

## Next Steps

1. **Frontend Integration**:
   - Create React components for email compose, inbox, templates
   - Implement rich text editor (e.g., TinyMCE, Quill)
   - Add cost center selector UI

2. **Production Configuration**:
   - Configure SMTP server (Gmail, SendGrid, AWS SES)
   - Set up email templates with branding
   - Configure email rate limiting (if needed)

3. **Optional Enhancements**:
   - Email attachments support
   - Template variable replacement
   - Scheduled email sending (Celery)
   - Email tracking (open rates, click rates)
   - Reply-to functionality

## Troubleshooting

### Issue: Migrations fail
**Solution**: Ensure `email_communication` is in `INSTALLED_APPS` before running migrations.

### Issue: Email not sending
**Solution**: Check `EMAIL_BACKEND` configuration and SMTP credentials in `.env` file.

### Issue: Permission denied
**Solution**: Check user role and permissions in `permissions.py`.

### Issue: Oracle compatibility
**Solution**: Models use hash-based indexing and avoid direct queries on encrypted fields.

## File Structure
```
email_communication/
├── __init__.py
├── admin.py              # Django admin configuration
├── apps.py               # App configuration
├── models.py             # 5 models with Oracle compatibility
├── managers.py           # Custom managers for queries
├── serializers.py        # DRF serializers
├── views.py              # API views and viewsets
├── urls.py               # URL routing
├── permissions.py        # Custom permissions
├── services.py           # EmailService business logic
├── tests.py              # Unit tests
└── migrations/
    └── 0001_initial.py   # Initial migration
```

## Support

For issues or questions:
1. Check the main documentation: `docs/EMAIL_COMMUNICATION_SYSTEM_PLAN.md`
2. Review the copilot instructions: `.github/copilot-instructions.md`
3. Check Django logs: `logs/django.log`

---

**Implementation Status**: ✅ Complete - Ready for frontend integration
**Database**: SQLite (dev) / Oracle (production compatible)
**Last Updated**: November 6, 2025
