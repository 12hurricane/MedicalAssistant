import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';

/// Fetches the adherence analysis.
/// For now, since there is no roster, we hardcode the `patient_id` parameter to 1
/// if requested, so we can test the populated states of the Clinician Dashboard.
final adherenceAnalysisProvider =
    FutureProvider.family<AdherenceAnalysisResult, int?>((ref, patientId) async {
  final client = ref.read(apiClientProvider);
  
  final queryParams = <String, dynamic>{};
  if (patientId != null) {
    queryParams['patient_id'] = patientId;
  }

  return client.getObject(
    ApiEndpoints.adherenceAnalysis,
    decode: AdherenceAnalysisResult.fromJson,
    query: queryParams,
  );
});
