# Project Scope Notes & Decisions

## Notifications & Reminders Scope

**Scope Decision:**
Push/local notifications are **IN SCOPE** for this MVP, with the known limitation that `flutter_local_notifications` has limited web support — notifications are scheduled on mobile only (Android/iOS). On web targets, notification scheduling calls safely no-op without blocking or raising unhandled exceptions.

### Specific Notification Behaviors Enforced:

1. **Local Timezone Alignment:**
   - Dose reminders are scheduled using the patient's registered IANA timezone (captured during onboarding and stored on the `Patient` model, e.g. `Asia/Karachi`).
   - UTC scheduled dose instants from the database (`scheduled_at`) are converted into the patient's zone via `tz.TZDateTime.from(scheduledTime.toUtc(), location)`.
   - The device notification triggers exactly when the patient's local wall clock reaches the scheduled time.

2. **Dose Status Suppression & Cancellation:**
   - Scheduled reminders are registered only for doses with `status == 'PENDING'`.
   - When a dose is confirmed as logged (`TAKEN`, `SKIPPED`, etc.), `todayScheduleProvider` triggers a synchronization cycle that explicitly invokes `NotificationService.cancelReminder(dose.scheduleId)`.
   - If a dose has already been logged before its scheduled time, no reminder will fire.
