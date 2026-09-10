import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';
import '../../../../shared/dose_status.dart';
import '../../medications/state/today_schedule_controller.dart';
import '../data/adherence_repository.dart';

final adherenceRepositoryProvider = Provider<AdherenceRepository>(
  (ref) => AdherenceRepository(client: ref.watch(apiClientProvider)),
);

/// The period the dashboard is showing. `7d` is the backend's default.
final adherencePeriodProvider = StateProvider<String>((ref) => '7d');

/// The signed-in patient's adherence metrics for [adherencePeriodProvider].
final adherenceMetricsProvider =
    AsyncNotifierProvider<AdherenceMetricsController, AdherenceMetricsResponse>(
  AdherenceMetricsController.new,
);

class AdherenceMetricsController extends AsyncNotifier<AdherenceMetricsResponse> {
  @override
  Future<AdherenceMetricsResponse> build() {
    final period = ref.watch(adherencePeriodProvider);
    return ref.watch(adherenceRepositoryProvider).fetchMetrics(period: period);
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }
}

/// Writes a dose outcome, then refetches everything it invalidates.
///
/// Kept separate from [todayScheduleProvider] because a write and a read have different
/// failure semantics: a failed refresh leaves stale data on screen, whereas a failed
/// write must reach the button that triggered it so the patient is not told a dose was
/// recorded when it was not. [log] therefore rethrows.
final doseLogControllerProvider =
    NotifierProvider<DoseLogController, DoseLogUiState>(DoseLogController.new);

/// Which dose is currently being written, if any.
///
/// Scoped to a single schedule id rather than a bare bool so only the row being logged
/// shows a spinner — a global "busy" flag would freeze every button on the list.
class DoseLogUiState {
  const DoseLogUiState({this.submittingScheduleId});

  final int? submittingScheduleId;

  bool isSubmitting(int scheduleId) => submittingScheduleId == scheduleId;
  bool get isBusy => submittingScheduleId != null;
}

class DoseLogController extends Notifier<DoseLogUiState> {
  @override
  DoseLogUiState build() => const DoseLogUiState();

  /// Records the outcome of one dose and refreshes the schedule and the metrics.
  ///
  /// The metrics refresh is the visible half of the milestone: a dose logged here has
  /// to move the adherence number, or the number is decoration.
  Future<DoseLogResponse> log({
    required int scheduleId,
    required DoseLogAction action,
    int? reminderId,
    SkipReasonCode? skipReasonCode,
    String? note,
  }) async {
    state = DoseLogUiState(submittingScheduleId: scheduleId);
    try {
      final logged = await ref.read(adherenceRepositoryProvider).logDose(
            scheduleId: scheduleId,
            action: action,
            reminderId: reminderId,
            skipReasonCode: skipReasonCode,
            note: note,
          );
      // Refetch both, and wait for them so the caller's sheet does not close over a
      // stale adherence number. A refresh failure is deliberately swallowed here: the
      // dose is already written, and rethrowing would tell the patient the log failed
      // and invite them to record the same dose twice. The providers hold their own
      // AsyncError, so the screen still shows that the refresh did not land.
      await Future.wait([
        _refreshQuietly(ref.read(todayScheduleProvider.notifier).refresh()),
        _refreshQuietly(ref.read(adherenceMetricsProvider.notifier).refresh()),
      ]);
      return logged;
    } finally {
      state = const DoseLogUiState();
    }
  }

  static Future<void> _refreshQuietly(Future<void> refresh) async {
    try {
      await refresh;
    } on Object {
      // Already recorded as AsyncError on the provider it came from.
    }
  }
}
