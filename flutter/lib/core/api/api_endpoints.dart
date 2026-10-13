/// Every backend path this client calls.
///
/// Kept as constants rather than string literals at the call sites so
/// `test/api_contract_test.dart` can assert that each one exists in the backend's
/// `openapi.json`. A typo'd path is otherwise a runtime 404 discovered by a patient.
class ApiEndpoints {
  const ApiEndpoints._();

  static const String v1 = '/api/v1';

  // --- auth ---
  static const String register = '$v1/auth/register';

  /// Form-encoded, not JSON: the backend takes an `OAuth2PasswordRequestForm`,
  /// so the field is `username` even though the value is an email address.
  static const String login = '$v1/auth/login';
  static const String refresh = '$v1/auth/refresh';
  static const String me = '$v1/auth/me';

  // --- patient ---
  static const String patients = '$v1/patients';
  static String patientProfile(int patientId) => '$v1/patients/$patientId';
  static const String myPatientProfile = '$v1/patients/me';
  static const String myPatientSafety = '$v1/patients/me/safety';

  /// Clinician-facing. Takes a patient id.
  static String patientSafety(int patientId) => '$v1/patients/$patientId/safety';

  // --- schedule ---
  static const String todaySchedule = '$v1/schedule/today';

  /// Clinician-facing: audit trail for a schedule.
  static String scheduleVersions(int scheduleId) =>
      '$v1/schedule/$scheduleId/versions';

  // --- adherence ---
  static const String logDose = '$v1/adherence/log';
  static const String adherenceScore = '$v1/adherence/score';
  static const String adherenceAnalysis = '$v1/adherence/analysis';

  /// Clinician-facing: correct a mislogged dose event.
  static String correctEvent(int eventId) =>
      '$v1/adherence/events/$eventId/correct';

  // --- prescriptions ---
  static const String prescriptions = '$v1/prescriptions';
  static const String uploadPrescription = '$v1/prescriptions/upload';

  static String prescription(int id) => '$v1/prescriptions/$id';

  static String verifyPrescription(int id) => '$v1/prescriptions/$id/verify';

  // --- medications catalogue (admin/lookup, not the patient's doses) ---
  static const String medications = '$v1/medications';

  static String medication(int id) => '$v1/medications/$id';

  static const String health = '$v1/health';

  // --- agent ---
  static const String agentChat = '$v1/agent/chat';

  /// Templated forms of the parameterised paths, exactly as OpenAPI spells them.
  /// The contract test resolves these against the spec.
  static const List<String> allTemplates = [
    register,
    login,
    refresh,
    me,
    patients,
    '$v1/patients/{patient_id}',
    myPatientProfile,
    myPatientSafety,
    '$v1/patients/{patient_id}/safety',
    todaySchedule,
    '$v1/schedule/{schedule_id}/versions',
    logDose,
    adherenceScore,
    adherenceAnalysis,
    '$v1/adherence/events/{event_id}/correct',
    prescriptions,
    '$v1/prescriptions/{id}',
    '$v1/prescriptions/{id}/verify',
    medications,
    '$v1/medications/{id}',
    health,
    agentChat,
  ];
}
