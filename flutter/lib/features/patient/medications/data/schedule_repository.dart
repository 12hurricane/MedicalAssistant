import '../../../../core/api/api_client.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/api/generated/api_models.dart';

/// The signed-in patient's dose list for today.
class ScheduleRepository {
  ScheduleRepository({required ApiClient client}) : _client = client;

  final ApiClient _client;

  /// `GET /api/v1/schedule/today`.
  ///
  /// Takes no date argument on purpose: "today" is the patient's local calendar day,
  /// resolved from their stored timezone on the server. A client-supplied date would
  /// be the device's idea of today, which is wrong the moment someone travels — and
  /// wrong in the worst way, because it would silently shift which doses are shown.
  Future<TodayScheduleResponse> fetchToday() => _client.getObject(
        ApiEndpoints.todaySchedule,
        decode: TodayScheduleResponse.fromJson,
      );
}
