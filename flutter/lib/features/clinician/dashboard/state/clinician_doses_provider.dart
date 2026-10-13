import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/api/generated/api_models.dart';
import '../data/clinician_dose_repository.dart';

/// Fetches authoritative today's doses and events for an assigned patient.
final clinicianDosesProvider =
    FutureProvider.family<TodayScheduleResponse, int>((ref, patientId) async {
  if (patientId <= 0) {
    throw ArgumentError.value(patientId, 'patientId', 'Invalid patient ID');
  }

  final repository = ref.watch(clinicianDoseRepositoryProvider);
  return repository.fetchPatientDoses(patientId);
});
