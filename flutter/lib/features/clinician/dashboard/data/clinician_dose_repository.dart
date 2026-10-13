import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/api/api_client.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';

final clinicianDoseRepositoryProvider = Provider<ClinicianDoseRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  return ClinicianDoseRepository(client: client);
});

/// Repository for clinician dose-event retrieval and correction.
class ClinicianDoseRepository {
  const ClinicianDoseRepository({required ApiClient client}) : _client = client;

  final ApiClient _client;

  /// Fetches authoritative today's schedule and events for an assigned patient:
  /// `GET /api/v1/schedule/today?patient_id={patientId}`
  Future<TodayScheduleResponse> fetchPatientDoses(int patientId) {
    return _client.getObject(
      ApiEndpoints.todaySchedule,
      query: {'patient_id': patientId},
      decode: TodayScheduleResponse.fromJson,
    );
  }

  /// Submits an immutable dose-event correction:
  /// `POST /api/v1/adherence/events/{eventId}/correct`
  Future<EventCorrectionResponse> correctEvent({
    required int eventId,
    required String newStatus,
    required String reason,
  }) {
    return _client.postObject(
      ApiEndpoints.correctEvent(eventId),
      body: EventCorrectionRequest(
        newStatus: newStatus,
        reason: reason,
      ).toJson(),
      decode: EventCorrectionResponse.fromJson,
    );
  }
}
