# Forgot Password — API Endpoints

Base URL prefix: `/api/auth/`

All three endpoints are **public** (no authentication token required).

---

## Flow Summary

```
1. User submits their email
   POST /api/auth/forgot-password/
         ↓
   6-digit code emailed to the user (expires in 10 min)

2. User submits the code
   POST /api/auth/verify-reset-code/
         ↓
   Signed reset token returned (valid 10 min)

3. User submits the new password
   POST /api/auth/reset-password/
         ↓
   Password updated — flow complete
```

---

## Endpoint 1 — Request Reset Code

**`POST /api/auth/forgot-password/`**

Sends a 6-digit reset code to the provided email address.

### Request Body

```json
{
  "email": "user@example.com"
}
```

### Success Response — `200 OK`

Returned regardless of whether the email exists (prevents user enumeration).

```json
{
  "message": "If this email is registered, a reset code has been sent."
}
```

### Error Responses

| Condition | Status | Body |
|---|---|---|
| Azure AD account | `400` | `{ "detail": "This account uses Microsoft SSO. Please reset your password through the Azure portal." }` |
| Request within 1.5 min of last code | `429` | `{ "detail": "Please wait before requesting another code.", "retry_after_seconds": 75 }` |
| More than 5 codes requested in the past hour | `429` | `{ "detail": "Too many reset requests. Please try again later.", "retry_after_seconds": 3600 }` |
| Missing / invalid email field | `400` | `{ "errors": { "email": [...] } }` |

### Rules

- Azure AD users (`auth_type == "azure"`) are blocked — they must reset through the Azure portal.
- Always returns `200` when the email is not found (anti-enumeration protection).
- Maximum **5 codes per email per hour**.
- Minimum **90 seconds** between requests (resend cooldown).
- Requesting a new code **invalidates all previous unused codes** for that user.
- Code expires **10 minutes** after it is created.

---

## Endpoint 2 — Verify Reset Code

**`POST /api/auth/verify-reset-code/`**

Verifies the 6-digit code and returns a short-lived signed token.

### Request Body

```json
{
  "email": "user@example.com",
  "code": "482031"
}
```

### Success Response — `200 OK`

```json
{
  "token": "<signed_token>"
}
```

The token must be passed to endpoint 3. It is valid for **10 minutes**.

### Error Responses

| Condition | Status | Body |
|---|---|---|
| Wrong code | `400` | `{ "detail": "Invalid or expired reset code." }` |
| Expired code | `400` | `{ "detail": "Invalid or expired reset code." }` |
| Code already used | `400` | `{ "detail": "Invalid or expired reset code." }` |
| Unknown email | `400` | `{ "detail": "Invalid code or email." }` |
| Code is not exactly 6 digits | `400` | `{ "errors": { "code": [...] } }` |

### Notes

- The code is **not** marked as used at this step — only consumed when the password is actually changed.
- The signed token uses `django.core.signing` — it is tamper-proof and self-expiring.

---

## Endpoint 3 — Reset Password

**`POST /api/auth/reset-password/`**

Sets a new password using the signed token obtained from endpoint 2.

### Request Body

```json
{
  "token": "<signed_token>",
  "new_password": "NewSecure@Pass1",
  "confirm_password": "NewSecure@Pass1"
}
```

### Success Response — `200 OK`

```json
{
  "message": "Password has been reset successfully."
}
```

### Error Responses

| Condition | Status | Body |
|---|---|---|
| Token expired (> 10 min old) | `400` | `{ "detail": "Reset token has expired. Please request a new code." }` |
| Token tampered / invalid | `400` | `{ "detail": "Invalid reset token." }` |
| Code already used | `400` | `{ "detail": "Reset code has already been used or is invalid." }` |
| Code expired | `400` | `{ "detail": "Reset code has expired. Please request a new one." }` |
| Passwords do not match | `400` | `{ "errors": ["Passwords do not match."] }` |
| Password too short (< 8 chars) | `400` | `{ "errors": { "new_password": [...] } }` |
| Password fails Django strength rules | `400` | `{ "errors": { "new_password": [...] } }` |
| Missing fields | `400` | `{ "errors": { ... } }` |

### Notes

- After a successful reset, **all remaining unused reset codes** for the user are invalidated.
- Password strength rules match `ChangePasswordView` (Django's built-in validators).

---

## Database Model — `PasswordResetCode`

Table: `auth_password_reset_code`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `user` | FK → User | CASCADE on delete |
| `code_hash` | `VARCHAR(64)` | SHA-256 hex of the 6-digit code |
| `created_at` | DateTime | Set at creation |
| `expires_at` | DateTime | `created_at + 10 minutes` |
| `is_used` | Boolean | `True` = consumed or invalidated |
| `ip_address` | IP (nullable) | Requester IP for audit |

---

## Periodic Cleanup

Stale records (expired or used codes older than 24 hours) can be removed with:

```bash
python manage.py cleanup_expired_reset_codes
```

Recommended: schedule as a daily cron job.

```bash
# Example cron entry (daily at 2am)
0 2 * * * /path/to/venv/bin/python /path/to/project/manage.py cleanup_expired_reset_codes
```

---

## Security Highlights

| Concern | Mitigation |
|---|---|
| User enumeration | `forgot-password` always returns `200`, even for unknown emails |
| Brute-force code guessing | Rate limit (5/hr) + 90-second resend cooldown + code expiry |
| Code storage | SHA-256 hash stored — plaintext code never persisted |
| Token forgery | `django.core.signing` — cryptographically signed + auto-expiring |
| Azure AD mixing | Azure users explicitly blocked with a clear message |
| Replay attacks | Code invalidated after use; new request invalidates previous codes |

---

## Files Added / Modified

| File | Change |
|---|---|
| `authentication/models.py` | Added `PasswordResetCode` model |
| `authentication/migrations/0002_add_password_reset_code.py` | Migration for the new model |
| `authentication/email_utils.py` | `send_password_reset_email()` — bilingual RTL email |
| `authentication/serializers.py` | Added `ForgotPasswordSerializer`, `VerifyResetCodeSerializer`, `SetNewPasswordSerializer` |
| `authentication/views.py` | Added `ForgotPasswordView`, `VerifyResetCodeView`, `ResetPasswordView` |
| `authentication/urls.py` | Added 3 URL patterns |
| `authentication/management/commands/cleanup_expired_reset_codes.py` | Cleanup management command |
| `authentication/tests_forgot_password.py` | 28 tests — all passing |
