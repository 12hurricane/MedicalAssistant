import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';

/// Fetches the full safety assessment for a patient.
///
/// Used by the Organ Impact Viewer to display deterministic safety findings,
/// evidence chain, and interaction details.
final safetyAssessmentProvider =
    FutureProvider.family<SafetyAssessmentResponse, int>((ref, patientId) async {
  final client = ref.read(apiClientProvider);

  return client.getObject(
    ApiEndpoints.patientSafety(patientId),
    decode: SafetyAssessmentResponse.fromJson,
  );
});
