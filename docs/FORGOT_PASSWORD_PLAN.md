# Forgot Password Feature — Implementation Plan

## Overview

Add a 3-step forgot password flow (**Request Code → Verify Code → Reset Password**) with 6-digit email codes, rate limiting, bilingual email, DB-stored hashed codes with periodic cleanup, and full-stack implementation (Django API + Vue.js pages).

> **Scope:** Forgot password is for **regular (email/password) users only**. Azure AD users authenticate via Microsoft SSO and must reset their password through the Azure portal — attempting to use this flow will return a clear error message.

### Flow Summary

```
User enters email
      ↓
[POST /api/auth/forgot-password/]
      ↓
6-digit code emailed (expires in 10 min)
      ↓
User enters code
      ↓
[POST /api/auth/verify-reset-code/]
      ↓
Signed token returned (valid 10 min)
      ↓
User enters new password
      ↓
[POST /api/auth/reset-password/]
      ↓
Password updated ✓
```

---

## Phase 1 — Backend: Model & Migration

### Step 1 — `PasswordResetCode` model in `authentication/models.py`

| Field | Type | Notes |
|---|---|---|
| `id` | UUIDField (PK) | Auto-generated |
| `user` | ForeignKey → User | On delete CASCADE |
| `code_hash` | CharField(64) | SHA256 of the 6-digit code — never store plaintext |
| `created_at` | DateTimeField | Auto now |
| `expires_at` | DateTimeField | Default = now + 10 minutes |
| `is_used` | BooleanField | Default False |
| `ip_address` | GenericIPAddressField | Nullable — for audit |

- Index on `(user, is_used, expires_at)` for efficient lookups
- Helper methods: `is_expired()`, `mark_used()`

### Step 2 — Migration

- `python manage.py makemigrations authentication`
- Must work with both SQLite (dev) and Oracle (production), following existing Oracle-compatible migration patterns in `authentication/migrations/`

---

## Phase 2 — Backend: Email Utility

### Step 3 — `authentication/email_utils.py` *(parallel with Step 4)*

Function: `send_password_reset_email(user, code)`

- Bilingual HTML email (Arabic + English) with RTL support
- Use `EmailMultiAlternatives` (same pattern as `email_communication/services.py` → `wrap_html_with_rtl()`)
- Use `settings.DEFAULT_FROM_EMAIL` as sender
- Email content:
  - Prominent 6-digit code display
  - 10-minute expiry warning
  - "If you didn't request this, ignore this email" disclaimer

---

## Phase 3 — Backend: Serializers, Views, URLs

### Step 4 — Serializers in `authentication/serializers.py` *(parallel with Step 3)*

| Serializer | Fields | Validation |
|---|---|---|
| `ForgotPasswordSerializer` | `email` | Field exists in DB; sanitize input |
| `VerifyResetCodeSerializer` | `email`, `code` | Code must be exactly 6 digits |
| `SetNewPasswordSerializer` | `token`, `new_password`, `confirm_password` | Passwords match; strength rules same as `ChangePasswordSerializer` |

### Step 5 — Views in `authentication/views.py` *(depends on Steps 3 & 4)*

All 3 views: `permission_classes = [AllowAny]` (unauthenticated endpoints)

#### A. `ForgotPasswordView` — `POST /api/auth/forgot-password/`
- Validate email from request
- **Block Azure AD users early**: if `user.auth_type == 'azure'`, return `400` with a clear message:
  > *"This account uses Microsoft SSO. Please reset your password through the Azure portal."*
- **Rate limit**: max 5 codes per email per hour (query `PasswordResetCode` count in last 60min)
- **Resend cooldown**: reject if last code for this email was created < 1.5 minutes ago
- Invalidate all previous unused codes for this user (set `is_used=True`)
- Generate code: `secrets.randbelow(900000) + 100000` (cryptographically random)
- Store `SHA256(code)` in `PasswordResetCode`
- Send email with plaintext code
- **Always return 200** even if email not found (anti-enumeration — prevents attackers from discovering registered emails)
- Log event via `log_security_event()`

#### B. `VerifyResetCodeView` — `POST /api/auth/verify-reset-code/`
- Look up user by email, find latest unused non-expired `PasswordResetCode`
- Compare `SHA256(submitted_code)` against stored `code_hash`
- On match: return a short-lived signed token using `django.core.signing.dumps(user_id, max_age=600)`
- On failure: return generic `400` error (no detail leak)
- Do NOT mark code as used yet — user hasn't reset the password yet

#### C. `ResetPasswordView` — `POST /api/auth/reset-password/`
- Accept `token`, `new_password`, `confirm_password`
- Verify token via `signing.loads(token, max_age=600)`
- Set password: `user.set_password(new_password)`
- Mark all reset codes for this user as used
- Log security event
- Return success

### Step 6 — URL patterns in `authentication/urls.py`

```
POST   /api/auth/forgot-password/
POST   /api/auth/verify-reset-code/
POST   /api/auth/reset-password/
```

---

## Phase 4 — Backend: Cleanup

### Step 7 — Management command *(parallel with Steps 5–6)*

File: `authentication/management/commands/cleanup_expired_reset_codes.py`

- Deletes `PasswordResetCode` records where:
  - `expires_at < now - 24 hours`, OR
  - `is_used=True AND created_at < now - 24 hours`
- Log count of deleted records
- Intended to run via OS cron or task scheduler

```bash
# Example cron (daily at 2am)
0 2 * * * python manage.py cleanup_expired_reset_codes
```

---

## Phase 5 — Frontend: Vue.js Pages

### Step 8 — `src/pages/Auth/ForgotPassword.vue` *(depends on Step 6)*

3-step wizard, matching Login.vue's design:
- Glassmorphism card, RTL Arabic, floating particles
- Same color palette: `#AE5D5A` → `#CFA365`
- Tajawal Arabic font

| Step | Content |
|---|---|
| Step 1 | Email input + "Send Code" button |
| Step 2 | 6 individual digit input boxes + resend countdown (1.5min) + "Verify" button |
| Step 3 | New password + Confirm password + "Reset Password" button + success state |

Create alongside: `src/composables/useForgotPassword.ts`
- State: `step`, `email`, `code`, `token`, `isLoading`, `error`, `resendCooldown`, `requestsRemaining`
- Methods: `requestCode()`, `verifyCode()`, `resetPassword()`, `startResendTimer()`

### Step 9 — API functions in `src/services/jwtAuthService.ts` *(parallel with Step 8)*

```typescript
authAPI.forgotPassword(email: string)
authAPI.verifyResetCode(email: string, code: string)
authAPI.resetPassword(token: string, newPassword: string, confirmPassword: string)
```

### Step 10 — Route in `src/router/index.ts`

```typescript
{
  path: '/forgot-password',
  component: () => import('@/pages/Auth/ForgotPassword.vue'),
  meta: { requiresGuest: true, hideNavigation: true }
}
```

### Step 11 — "Forgot Password?" link on `src/pages/Auth/Login.vue`

- Add `<router-link to="/forgot-password">` below the email/password form
- Styled consistently with existing Login.vue design

---

## Phase 6 — Testing

### Step 12 — `authentication/tests_forgot_password.py`

| # | Test Case |
|---|---|
| 1 | Request code for valid email → 200, code created in DB, email sent |
| 2 | Request code for non-existent email → 200 (no enumeration) |
| 3 | Request code within 1.5min cooldown → 429 with retry-after header |
| 4 | Request 6th code in one hour → 429 rate limit |
| 5 | Verify correct code → 200 with signed token |
| 6 | Verify wrong code → 400 |
| 7 | Verify expired code → 400 |
| 8 | Reset password with valid token → 200, password updated |
| 9 | Reset password with expired token → 400 |
| 10 | Reset password with mismatched passwords → 400 |
| 11 | Azure AD user can request reset (sets local password) |
| 12 | Old codes invalidated when new code is requested |
| 13 | All codes invalidated after successful reset |

### Step 13 — Manual Verification

```bash
# Backend tests
cd "ADJD WeaponBackend"
python manage.py test authentication.tests_forgot_password --verbosity=2

# Cleanup command
python manage.py cleanup_expired_reset_codes

# Start backend dev server
python manage.py runserver
```

```bash
# Frontend dev server
cd ADJD_SURVEY_FRONTEND
npm run dev
# Navigate to /forgot-password and walk through the full flow
# Email output visible in console (DEBUG=True uses console email backend)
```

**Rate limiting verification:**
- Send 5 codes in quick succession → 6th should be rejected with 429
- Send a code → resend within 90 seconds → should be rejected with 429 and retry-after

---

## Files to Modify / Create

### Backend — Modify

| File | Change |
|---|---|
| `authentication/models.py` | Add `PasswordResetCode` model |
| `authentication/serializers.py` | Add 3 serializers |
| `authentication/views.py` | Add 3 view classes |
| `authentication/urls.py` | Add 3 URL patterns |

### Backend — Create

| File | Purpose |
|---|---|
| `authentication/email_utils.py` | Password reset email sender |
| `authentication/management/commands/cleanup_expired_reset_codes.py` | Periodic DB cleanup |
| `authentication/tests_forgot_password.py` | Full test suite |

### Frontend — Modify

| File | Change |
|---|---|
| `src/services/jwtAuthService.ts` | Add 3 API functions to `authAPI` |
| `src/router/index.ts` | Add `/forgot-password` route |
| `src/pages/Auth/Login.vue` | Add "Forgot Password?" link |

### Frontend — Create

| File | Purpose |
|---|---|
| `src/pages/Auth/ForgotPassword.vue` | 3-step wizard page |
| `src/composables/useForgotPassword.ts` | Composable for state/logic |

---

## Security Decisions

| Decision | Choice | Reason |
|---|---|---|
| Code storage | SHA256 hash in DB | Code exposure if DB is compromised is mitigated |
| Anti-enumeration | Always return 200 on forgot-password | Prevents discovering registered emails |
| Reset authorization | `django.core.signing` signed token | Tamper-proof, no extra DB lookup, auto-expiring |
| Azure AD users | **Blocked with clear message** | Azure users must reset via Azure portal; mixing auth systems causes security issues |
| Code invalidation | Previous codes invalidated on new request | Prevents replay with old codes |

---

---

## Test Credentials (Local SQLite DB)

Use these accounts to test the forgot password flow locally. All are `regular` auth type and `super_admin` role.

| Email | Password | Notes |
|---|---|---|
| `admin@test.com` | `Admin@1234` | Primary test account |
| `superadmin@example.com` | `Admin@1234` | Secondary test account |

> **Note:** Password was explicitly set via `user.set_password()` on the local SQLite DB for testing.
> Azure AD accounts (if any exist in DB) will be **blocked** by the forgot password flow — they must use SSO.

---

## Open Questions (Confirm Before Implementation)

1. **Account lockout on failed verify attempts** — Should we block after 5 wrong code entries for 15 minutes?
   - *Recommendation: Yes — prevents brute-forcing the 6-digit code (1,000,000 combinations)*

2. **Confirmation email after reset** — Send "your password was changed" notification to the user?
   - *Recommendation: Yes — alerts user if they didn't initiate the reset*

3. **Password strength rules** — Match existing `ChangePasswordSerializer` rules or add stricter ones?
   - *Recommendation: Match existing for consistency*
