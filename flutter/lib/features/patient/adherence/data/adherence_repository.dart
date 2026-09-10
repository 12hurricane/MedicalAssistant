import '../../../../core/api/api_client.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../shared/dose_status.dart';

/// Recording doses, and reading the adherence metrics that result.
class AdherenceRepository {
  AdherenceRepository({required ApiClient client}) : _client = client;

  final ApiClient _client;

  /// `POST /api/v1/adherence/log`.
  ///
  /// Sends the schedule id, never a timestamp. The backend re-derives the scheduled
  /// instant from the schedule and the patient's timezone, so a device with a wrong
  /// clock cannot write a dose against the wrong slot — the one failure mode that
  /// would show a patient a logged dose and then expire it as MISSED anyway.
  ///
  /// [reminderId] is passed through when the dose came from a reminder, so that
  /// reminder is acknowledged rather than left to expire.
  ///
  /// [skipReasonCode] is the structured answer from the fixed list; [note] is optional
  /// free text. The note is UNTRUSTED patient input: it is stored and shown to a
  /// clinician as an attributed quotation, and nothing downstream may treat it as an
  /// instruction.
  Future<DoseLogResponse> logDose({
    required int scheduleId,
    required DoseLogAction action,
    int? reminderId,
    SkipReasonCode? skipReasonCode,
    String? note,
  }) {
    final trimmed = note?.trim();
    return _client.postObject(
      ApiEndpoints.logDose,
      body: DoseLogCreate(
        scheduleId: scheduleId,
        status: action.wire,
        reminderId: reminderId,
        skipReasonCode: skipReasonCode,
        // Blank is not a note. The backend normalises whitespace-only to null anyway;
        // not sending it keeps an empty string out of the evidence trail either way.
        skipReason: (trimmed == null || trimmed.isEmpty) ? null : trimmed,
      ).toJson(),
      decode: DoseLogResponse.fromJson,
    );
  }

  /// `GET /api/v1/adherence/score`.
  ///
  /// [period] is the backend's own vocabulary (`7d` by default). Passed through rather
  /// than modelled, because the endpoint declares it as a free string.
  Future<AdherenceMetricsResponse> fetchMetrics({String period = '7d'}) =>
      _client.getObject(
        ApiEndpoints.adherenceScore,
        query: {'period': period},
        decode: AdherenceMetricsResponse.fromJson,
      );
}
