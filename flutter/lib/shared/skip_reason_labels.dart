import '../core/api/generated/api_models.dart';

/// Patient-facing wording for each [SkipReasonCode].
///
/// The order is the order they appear in the sheet, and it is not alphabetical:
/// "Doctor instructed me" comes first because it is the one answer that means the skip
/// was *correct*. A patient following instructions should not have to scroll past five
/// suggestions that they failed at something.
///
/// The wire values are the backend's, unchanged. The role enum and the skip-reason enum
/// now agree on CLINICIAN (backend migration `9f2c1d7ab4e0` retired DOCTOR), so the
/// split this comment used to describe is gone from the schema.
///
/// The patient-facing label deliberately still says "Doctor". That is not a leftover:
/// technical role values and display copy are separate layers, and "doctor" is simply
/// the word a patient uses. "Clinician-instructed" is accurate and reads like a form.
const List<SkipReasonCode> kSkipReasonOrder = [
  SkipReasonCode.clinicianInstructed,
  SkipReasonCode.sideEffects,
  SkipReasonCode.unavailable,
  SkipReasonCode.cost,
  SkipReasonCode.scheduleConflict,
  SkipReasonCode.other,
];

extension SkipReasonLabel on SkipReasonCode {
  String get patientLabel => switch (this) {
        SkipReasonCode.clinicianInstructed => 'Doctor instructed me',
        SkipReasonCode.sideEffects => 'Side effects',
        SkipReasonCode.unavailable => 'Medication unavailable',
        SkipReasonCode.cost => 'Cost',
        SkipReasonCode.scheduleConflict => 'Schedule conflict',
        SkipReasonCode.other => 'Other',
      };

  /// Shown to a clinician reviewing the record. Same fact, different audience.
  String get clinicianLabel => switch (this) {
        SkipReasonCode.clinicianInstructed => 'Clinician-instructed',
        SkipReasonCode.sideEffects => 'Side effects',
        SkipReasonCode.unavailable => 'Medication unavailable',
        SkipReasonCode.cost => 'Cost barrier',
        SkipReasonCode.scheduleConflict => 'Schedule conflict',
        SkipReasonCode.other => 'Other (see note)',
      };
}

/// Tolerant lookup for a code that arrives as a bare string.
///
/// `TodayDoseResponse.skip_reason_code` and `DoseLogResponse.skip_reason_code` are typed
/// `str` in the schema even though the request side is a real enum, so a value this
/// build does not know is possible. Returns null rather than throwing: a stale label on
/// a historical record should not take down the schedule screen.
SkipReasonCode? skipReasonCodeOrNull(String? wire) {
  if (wire == null) return null;
  final normalised = wire.trim().toUpperCase();
  for (final code in SkipReasonCode.values) {
    if (code.wire == normalised) return code;
  }
  return null;
}
