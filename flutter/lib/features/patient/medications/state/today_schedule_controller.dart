import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';
import '../../../../core/notifications/notification_service.dart';
import '../../../../shared/time_utils.dart';
import '../data/schedule_repository.dart';

final scheduleRepositoryProvider = Provider<ScheduleRepository>(
  (ref) => ScheduleRepository(client: ref.watch(apiClientProvider)),
);

/// Today's doses, straight from the backend.
///
/// No client-side caching beyond what Riverpod keeps for the current listeners, and no
/// optimistic local mutation. A dose's status is a clinical record; the only copy worth
/// rendering is the one the server just confirmed. Logging a dose therefore refetches
/// rather than patching the list in place — [ref.invalidateSelf] keeps the previous
/// list on screen while the refetch is in flight, so the screen does not flash empty.
final todayScheduleProvider =
    AsyncNotifierProvider<TodayScheduleController, TodayScheduleResponse>(
  TodayScheduleController.new,
);

class TodayScheduleController extends AsyncNotifier<TodayScheduleResponse> {
  @override
  Future<TodayScheduleResponse> build() async {
    final raw = await ref.watch(scheduleRepositoryProvider).fetchToday();

    // Ensure every dose's local time is explicitly converted from scheduledAt (UTC)
    // to the patient's registered timezone:
    final convertedDoses = raw.doses.map((dose) {
      final localTime = formatUtcToPatientTime(
        dose.scheduledAt,
        raw.timezone,
        use24Hour: true,
      );
      return TodayDoseResponse(
        scheduleId: dose.scheduleId,
        medicineName: dose.medicineName,
        scheduledAt: dose.scheduledAt,
        scheduledLocalTime: localTime,
        status: dose.status,
        isDue: dose.isDue,
        eventId: dose.eventId,
        reminderId: dose.reminderId,
        strength: dose.strength,
        dose: dose.dose,
        instructions: dose.instructions,
        relationToMeal: dose.relationToMeal,
        confirmedAt: dose.confirmedAt,
        skipReasonCode: dose.skipReasonCode,
        skipReason: dose.skipReason,
      );
    }).toList();

    final schedule = TodayScheduleResponse(
      patientId: raw.patientId,
      localDate: raw.localDate,
      timezone: raw.timezone,
      doses: convertedDoses,
      totalDoses: raw.totalDoses,
      dosesTaken: raw.dosesTaken,
      dosesRemaining: raw.dosesRemaining,
    );

    try {
      final notifications = ref.read(notificationServiceProvider);
      for (final dose in schedule.doses) {
        if (dose.status == 'PENDING') {
          await notifications.scheduleDoseReminder(
            id: dose.scheduleId,
            medicationName: dose.medicineName,
            scheduledTime: dose.scheduledAt,
            timezoneName: schedule.timezone,
          );
        } else {
          // If the dose was already taken/skipped, ensure any pending notification is cancelled
          await notifications.cancelReminder(dose.scheduleId);
        }
      }
    } catch (_) {
      // Ignored if notifications fail (e.g. web fallback)
    }

    return schedule;
  }

  /// Pull-to-refresh, and the refetch after a dose is logged.
  Future<void> refresh() async {
    ref.invalidateSelf();
    // Awaited so a RefreshIndicator's spinner lasts as long as the request does.
    await future;
  }
}
