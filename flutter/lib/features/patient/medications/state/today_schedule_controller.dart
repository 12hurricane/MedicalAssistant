import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';
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
  Future<TodayScheduleResponse> build() =>
      ref.watch(scheduleRepositoryProvider).fetchToday();

  /// Pull-to-refresh, and the refetch after a dose is logged.
  Future<void> refresh() async {
    ref.invalidateSelf();
    // Awaited so a RefreshIndicator's spinner lasts as long as the request does.
    await future;
  }
}
