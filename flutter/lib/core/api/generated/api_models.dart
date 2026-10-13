// GENERATED FILE — DO NOT EDIT BY HAND.
//
// Source of truth: the backend OpenAPI schema.
// Regenerate with:  dart run tool/generate_api_models.dart
//
// Doc comments below are the backend's own field descriptions. If one
// reads wrong, fix it in the Python schema, not here.
//
// ignore_for_file: unnecessary_cast, prefer_single_quotes

/// A JSON value did not match the shape the schema promised.
///
/// Thrown rather than defaulted. A dose status or risk level that this
/// client does not recognise is a version mismatch with the backend, and
/// quietly substituting a fallback would show a patient or clinician a
/// value the server never sent.
class ApiSchemaMismatch implements Exception {
  ApiSchemaMismatch(this.message);

  final String message;

  @override
  String toString() => 'ApiSchemaMismatch: $message';
}

/// Date-only fields are transported as YYYY-MM-DD, not as a full instant.
String _encodeDate(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

enum BarrierCategory {
  forgetfulness('Forgetfulness'),
  scheduleConflict('Schedule conflict'),
  medicationMisunderstanding('Medication misunderstanding'),
  sideEffects('Side effects'),
  accessAvailability('Access / availability'),
  cost('Cost'),
  intentionalNonAdherence('Intentional non-adherence'),
  complexity('Complexity'),
  clinicianDirectedHold('Clinician-directed hold'),
  unknownInsufficientData('Unknown / Insufficient data'),
  ;

  const BarrierCategory(this.wire);

  /// The exact string the backend sends and expects.
  final String wire;

  static BarrierCategory fromWire(String wire) => values.firstWhere(
        (v) => v.wire == wire,
        orElse: () => throw ApiSchemaMismatch(
            'Unknown BarrierCategory "$wire" — this client is older than the backend'),
      );
}

enum ConfidenceLevel {
  high('HIGH'),
  medium('MEDIUM'),
  low('LOW'),
  ;

  const ConfidenceLevel(this.wire);

  /// The exact string the backend sends and expects.
  final String wire;

  static ConfidenceLevel fromWire(String wire) => values.firstWhere(
        (v) => v.wire == wire,
        orElse: () => throw ApiSchemaMismatch(
            'Unknown ConfidenceLevel "$wire" — this client is older than the backend'),
      );
}

enum EvidenceStatus {
  observed('OBSERVED'),
  inferred('INFERRED'),
  unknown('UNKNOWN'),
  ;

  const EvidenceStatus(this.wire);

  /// The exact string the backend sends and expects.
  final String wire;

  static EvidenceStatus fromWire(String wire) => values.firstWhere(
        (v) => v.wire == wire,
        orElse: () => throw ApiSchemaMismatch(
            'Unknown EvidenceStatus "$wire" — this client is older than the backend'),
      );
}

/// The roles only an existing ADMIN may hand out.
///
/// A separate enum from :class:`UserRole` rather than a validator over it, so that
/// PATIENT is not merely rejected by ``POST /admin/users`` — it is not expressible
/// in that request at all. Patients are created by self-service registration, which
/// is the one path that also builds their profile row.
///
/// Because this enum is the request contract, an unsupported role here is a 422 from
/// Pydantic before any handler runs. That is what makes the retired DOCTOR and
/// CAREGIVER values unwritable rather than merely unused.
enum PrivilegedRole {
  clinician('CLINICIAN'),
  admin('ADMIN'),
  ;

  const PrivilegedRole(this.wire);

  /// The exact string the backend sends and expects.
  final String wire;

  static PrivilegedRole fromWire(String wire) => values.firstWhere(
        (v) => v.wire == wire,
        orElse: () => throw ApiSchemaMismatch(
            'Unknown PrivilegedRole "$wire" — this client is older than the backend'),
      );
}

/// Closed vocabulary for *why* a dose was skipped, chosen by the patient from a
/// fixed list in the UI rather than typed.
///
/// This exists so the barrier classifier stops guessing. Keyword-matching free text
/// ("stomach" -> side effects) is a heuristic that is wrong in both directions, and
/// its output is presented to a clinician as OBSERVED evidence. A tapped option is
/// the patient's actual answer.
///
/// It is also the trust boundary. A value here is one of these constants or the
/// write is rejected, so it is safe to render into any downstream context. The
/// free-text ``skip_reason`` beside it is arbitrary patient input and is not.
enum SkipReasonCode {
  clinicianInstructed('CLINICIAN_INSTRUCTED'),
  sideEffects('SIDE_EFFECTS'),
  unavailable('UNAVAILABLE'),
  cost('COST'),
  scheduleConflict('SCHEDULE_CONFLICT'),
  other('OTHER'),
  ;

  const SkipReasonCode(this.wire);

  /// The exact string the backend sends and expects.
  final String wire;

  static SkipReasonCode fromWire(String wire) => values.firstWhere(
        (v) => v.wire == wire,
        orElse: () => throw ApiSchemaMismatch(
            'Unknown SkipReasonCode "$wire" — this client is older than the backend'),
      );
}

/// Master output contract from the Adherence Analysis Service.
///
/// ``validation_passed`` refers to the deterministic invariant checks in
/// ResponseValidator (risk level preserved, human-review flag preserved, no unsafe
/// dosing advice, no untraceable citation). It is not a statement about a model.
class AdherenceAnalysisResult {
  const AdherenceAnalysisResult({
    required this.patientId,
    required this.evaluatedAt,
    required this.safetyRiskLevel,
    required this.requiresHumanReview,
    required this.recommendedAction,
    required this.patientExplanation,
    required this.clinicalBrief,
    this.validationPassed = true,
  });

  factory AdherenceAnalysisResult.fromJson(Map<String, dynamic> json) => AdherenceAnalysisResult(
        patientId: (json['patient_id'] as num).toInt(),
        evaluatedAt: DateTime.parse(json['evaluated_at'] as String),
        safetyRiskLevel: json['safety_risk_level'] as String,
        requiresHumanReview: json['requires_human_review'] as bool,
        recommendedAction: json['recommended_action'] as String,
        patientExplanation: PatientExplanation.fromJson(json['patient_explanation'] as Map<String, dynamic>),
        clinicalBrief: ClinicalBrief.fromJson(json['clinical_brief'] as Map<String, dynamic>),
        validationPassed: json['validation_passed'] == null ? true : json['validation_passed'] as bool,
      );

  final int patientId;

  final DateTime evaluatedAt;

  final String safetyRiskLevel;

  final bool requiresHumanReview;

  final String recommendedAction;

  final PatientExplanation patientExplanation;

  final ClinicalBrief clinicalBrief;

  final bool validationPassed;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['patient_id'] = patientId;
    json['evaluated_at'] = evaluatedAt.toIso8601String();
    json['safety_risk_level'] = safetyRiskLevel;
    json['requires_human_review'] = requiresHumanReview;
    json['recommended_action'] = recommendedAction;
    json['patient_explanation'] = patientExplanation.toJson();
    json['clinical_brief'] = clinicalBrief.toJson();
    json['validation_passed'] = validationPassed;
    return json;
  }
}

class AdherenceMetricsResponse {
  const AdherenceMetricsResponse({
    required this.patientId,
    required this.period,
    required this.periodStart,
    required this.periodEnd,
    required this.expectedDoses,
    required this.totalTaken,
    required this.totalMissed,
    required this.totalSkipped,
    required this.totalSnoozed,
    required this.currentStreak,
    required this.bestStreak,
    required this.timeSlotBreakdown,
    required this.dayOfWeekBreakdown,
    required this.trend,
    required this.detectedPatterns,
    required this.shouldEscalate,
    required this.escalationReasons,
    this.adherenceRate,
    this.missedRate,
    this.skippedRate,
  });

  factory AdherenceMetricsResponse.fromJson(Map<String, dynamic> json) => AdherenceMetricsResponse(
        patientId: (json['patient_id'] as num).toInt(),
        period: json['period'] as String,
        periodStart: DateTime.parse(json['period_start'] as String),
        periodEnd: DateTime.parse(json['period_end'] as String),
        expectedDoses: (json['expected_doses'] as num).toInt(),
        totalTaken: (json['total_taken'] as num).toInt(),
        totalMissed: (json['total_missed'] as num).toInt(),
        totalSkipped: (json['total_skipped'] as num).toInt(),
        totalSnoozed: (json['total_snoozed'] as num).toInt(),
        adherenceRate: json['adherence_rate'] == null ? null : (json['adherence_rate'] as num).toDouble(),
        missedRate: json['missed_rate'] == null ? null : (json['missed_rate'] as num).toDouble(),
        skippedRate: json['skipped_rate'] == null ? null : (json['skipped_rate'] as num).toDouble(),
        currentStreak: (json['current_streak'] as num).toInt(),
        bestStreak: (json['best_streak'] as num).toInt(),
        timeSlotBreakdown: (json['time_slot_breakdown'] as Map<String, dynamic>).map((k, e) => MapEntry(k, TimeSlotBreakdown.fromJson(e as Map<String, dynamic>))),
        dayOfWeekBreakdown: (json['day_of_week_breakdown'] as List<dynamic>).map((e) => DayOfWeekBreakdown.fromJson(e as Map<String, dynamic>)).toList(),
        trend: json['trend'] as String,
        detectedPatterns: (json['detected_patterns'] as List<dynamic>).map((e) => e as String).toList(),
        shouldEscalate: json['should_escalate'] as bool,
        escalationReasons: (json['escalation_reasons'] as List<dynamic>).map((e) => e as String).toList(),
      );

  final int patientId;

  final String period;

  final DateTime periodStart;

  final DateTime periodEnd;

  final int expectedDoses;

  final int totalTaken;

  final int totalMissed;

  final int totalSkipped;

  final int totalSnoozed;

  /// Null when there are no expected doses to divide by. A null rate means "not measurable", NOT zero and NOT 100%: render it as no-data (an em dash, a greyed bar) rather than substituting a number.
  final double? adherenceRate;

  /// Null when there are no expected doses to divide by. A null rate means "not measurable", NOT zero and NOT 100%: render it as no-data (an em dash, a greyed bar) rather than substituting a number.
  final double? missedRate;

  /// Null when there are no expected doses to divide by. A null rate means "not measurable", NOT zero and NOT 100%: render it as no-data (an em dash, a greyed bar) rather than substituting a number.
  final double? skippedRate;

  final int currentStreak;

  final int bestStreak;

  final Map<String, TimeSlotBreakdown> timeSlotBreakdown;

  final List<DayOfWeekBreakdown> dayOfWeekBreakdown;

  final String trend;

  final List<String> detectedPatterns;

  final bool shouldEscalate;

  final List<String> escalationReasons;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['patient_id'] = patientId;
    json['period'] = period;
    json['period_start'] = _encodeDate(periodStart);
    json['period_end'] = _encodeDate(periodEnd);
    json['expected_doses'] = expectedDoses;
    json['total_taken'] = totalTaken;
    json['total_missed'] = totalMissed;
    json['total_skipped'] = totalSkipped;
    json['total_snoozed'] = totalSnoozed;
    {
      final value = adherenceRate;
      if (value != null) {
        json['adherence_rate'] = value;
      }
    }
    {
      final value = missedRate;
      if (value != null) {
        json['missed_rate'] = value;
      }
    }
    {
      final value = skippedRate;
      if (value != null) {
        json['skipped_rate'] = value;
      }
    }
    json['current_streak'] = currentStreak;
    json['best_streak'] = bestStreak;
    json['time_slot_breakdown'] = timeSlotBreakdown.map((k, e) => MapEntry(k, e.toJson()));
    json['day_of_week_breakdown'] = dayOfWeekBreakdown.map((e) => e.toJson()).toList();
    json['trend'] = trend;
    json['detected_patterns'] = detectedPatterns;
    json['should_escalate'] = shouldEscalate;
    json['escalation_reasons'] = escalationReasons;
    return json;
  }
}

class AdherenceSafetyAlertResponse {
  const AdherenceSafetyAlertResponse({
    required this.adherenceRate,
    required this.consecutiveMissed,
    required this.criticalDrugsAffected,
    required this.clinicalRisk,
    required this.recommendedAction,
  });

  factory AdherenceSafetyAlertResponse.fromJson(Map<String, dynamic> json) => AdherenceSafetyAlertResponse(
        adherenceRate: (json['adherence_rate'] as num).toDouble(),
        consecutiveMissed: (json['consecutive_missed'] as num).toInt(),
        criticalDrugsAffected: (json['critical_drugs_affected'] as List<dynamic>).map((e) => e as String).toList(),
        clinicalRisk: json['clinical_risk'] as String,
        recommendedAction: json['recommended_action'] as String,
      );

  final double adherenceRate;

  final int consecutiveMissed;

  final List<String> criticalDrugsAffected;

  final String clinicalRisk;

  final String recommendedAction;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['adherence_rate'] = adherenceRate;
    json['consecutive_missed'] = consecutiveMissed;
    json['critical_drugs_affected'] = criticalDrugsAffected;
    json['clinical_risk'] = clinicalRisk;
    json['recommended_action'] = recommendedAction;
    return json;
  }
}

/// Privileged account creation. Reachable only by an authenticated ADMIN.
///
/// This is the only place ``role`` is writable over HTTP, and the values it accepts
/// are constrained by :class:`PrivilegedRole` rather than by :class:`UserRole`.
class AdminUserCreate {
  const AdminUserCreate({
    required this.name,
    required this.email,
    required this.password,
    required this.role,
    this.phone,
  });

  factory AdminUserCreate.fromJson(Map<String, dynamic> json) => AdminUserCreate(
        name: json['name'] as String,
        email: json['email'] as String,
        password: json['password'] as String,
        phone: json['phone'] == null ? null : json['phone'] as String,
        role: PrivilegedRole.fromWire(json['role'] as String),
      );

  final String name;

  final String email;

  /// Between 8 and 128 characters. No character-class requirements.
  final String password;

  final String? phone;

  final PrivilegedRole role;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['name'] = name;
    json['email'] = email;
    json['password'] = password;
    {
      final value = phone;
      if (value != null) {
        json['phone'] = value;
      }
    }
    json['role'] = role.wire;
    return json;
  }
}

class AgentChatRequest {
  const AgentChatRequest({
    required this.message,
  });

  factory AgentChatRequest.fromJson(Map<String, dynamic> json) => AgentChatRequest(
        message: json['message'] as String,
      );

  /// The patient's message to the AI agent.
  final String message;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['message'] = message;
    return json;
  }
}

class AgentChatResponse {
  const AgentChatResponse({
    required this.response,
  });

  factory AgentChatResponse.fromJson(Map<String, dynamic> json) => AgentChatResponse(
        response: json['response'] as String,
      );

  /// The AI agent's response text.
  final String response;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['response'] = response;
    return json;
  }
}

/// Structured adherence barrier hypothesis.
///
/// The two text fields have different trust levels and must not be merged:
///
/// - ``observed_pattern`` is composed by this system from its own numbers. Trusted.
/// - ``patient_reported_text`` is whatever the patient typed. UNTRUSTED. It is
///   carried in its own field precisely so a downstream consumer never has to
///   string-parse it back out of trusted prose, and so a prompt builder can place
///   it inside a fenced untrusted block instead of concatenating it into
///   instructions. See ``app/llm/prompt.py``.
class BarrierItem {
  const BarrierItem({
    required this.category,
    required this.status,
    required this.confidence,
    required this.observedPattern,
    required this.hypothesisRationale,
    required this.followUpQuestion,
    this.patientReportedText,
  });

  factory BarrierItem.fromJson(Map<String, dynamic> json) => BarrierItem(
        category: BarrierCategory.fromWire(json['category'] as String),
        status: EvidenceStatus.fromWire(json['status'] as String),
        confidence: ConfidenceLevel.fromWire(json['confidence'] as String),
        observedPattern: json['observed_pattern'] as String,
        hypothesisRationale: json['hypothesis_rationale'] as String,
        followUpQuestion: json['follow_up_question'] as String,
        patientReportedText: json['patient_reported_text'] == null ? null : json['patient_reported_text'] as String,
      );

  final BarrierCategory category;

  final EvidenceStatus status;

  final ConfidenceLevel confidence;

  final String observedPattern;

  final String hypothesisRationale;

  final String followUpQuestion;

  final String? patientReportedText;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['category'] = category.wire;
    json['status'] = status.wire;
    json['confidence'] = confidence.wire;
    json['observed_pattern'] = observedPattern;
    json['hypothesis_rationale'] = hypothesisRationale;
    json['follow_up_question'] = followUpQuestion;
    {
      final value = patientReportedText;
      if (value != null) {
        json['patient_reported_text'] = value;
      }
    }
    return json;
  }
}

class BodyLoginApiV1AuthLoginPost {
  const BodyLoginApiV1AuthLoginPost({
    required this.username,
    required this.password,
    this.grantType,
    this.scope = '',
    this.clientId,
    this.clientSecret,
  });

  factory BodyLoginApiV1AuthLoginPost.fromJson(Map<String, dynamic> json) => BodyLoginApiV1AuthLoginPost(
        grantType: json['grant_type'] == null ? null : json['grant_type'] as String,
        username: json['username'] as String,
        password: json['password'] as String,
        scope: json['scope'] == null ? '' : json['scope'] as String,
        clientId: json['client_id'] == null ? null : json['client_id'] as String,
        clientSecret: json['client_secret'] == null ? null : json['client_secret'] as String,
      );

  final String? grantType;

  final String username;

  final String password;

  final String scope;

  final String? clientId;

  final String? clientSecret;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    {
      final value = grantType;
      if (value != null) {
        json['grant_type'] = value;
      }
    }
    json['username'] = username;
    json['password'] = password;
    json['scope'] = scope;
    {
      final value = clientId;
      if (value != null) {
        json['client_id'] = value;
      }
    }
    {
      final value = clientSecret;
      if (value != null) {
        json['client_secret'] = value;
      }
    }
    return json;
  }
}

/// Clinician-facing adherence review and barrier brief.
class ClinicalBrief {
  const ClinicalBrief({
    required this.patientId,
    required this.period,
    required this.safetyRiskLevel,
    required this.requiresHumanReview,
    this.adherenceRate,
    this.citations,
    this.insights,
  });

  factory ClinicalBrief.fromJson(Map<String, dynamic> json) => ClinicalBrief(
        patientId: (json['patient_id'] as num).toInt(),
        period: json['period'] as String,
        adherenceRate: json['adherence_rate'] == null ? null : (json['adherence_rate'] as num).toDouble(),
        safetyRiskLevel: json['safety_risk_level'] as String,
        requiresHumanReview: json['requires_human_review'] as bool,
        citations: json['citations'] == null ? null : (json['citations'] as List<dynamic>).map((e) => e as String).toList(),
        insights: json['insights'] == null ? null : GenerativeClinicalInsights.fromJson(json['insights'] as Map<String, dynamic>),
      );

  final int patientId;

  final String period;

  final double? adherenceRate;

  final String safetyRiskLevel;

  final bool requiresHumanReview;

  final List<String>? citations;

  final GenerativeClinicalInsights? insights;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['patient_id'] = patientId;
    json['period'] = period;
    {
      final value = adherenceRate;
      if (value != null) {
        json['adherence_rate'] = value;
      }
    }
    json['safety_risk_level'] = safetyRiskLevel;
    json['requires_human_review'] = requiresHumanReview;
    {
      final value = citations;
      if (value != null) {
        json['citations'] = value;
      }
    }
    {
      final value = insights;
      if (value != null) {
        json['insights'] = value.toJson();
      }
    }
    return json;
  }
}

class ContraindicationAlertResponse {
  const ContraindicationAlertResponse({
    required this.medication,
    required this.contraindicationType,
    required this.trigger,
    required this.severity,
    required this.clinicalRisk,
    required this.recommendation,
  });

  factory ContraindicationAlertResponse.fromJson(Map<String, dynamic> json) => ContraindicationAlertResponse(
        medication: json['medication'] as String,
        contraindicationType: json['contraindication_type'] as String,
        trigger: json['trigger'] as String,
        severity: json['severity'] as String,
        clinicalRisk: json['clinical_risk'] as String,
        recommendation: json['recommendation'] as String,
      );

  final String medication;

  final String contraindicationType;

  final String trigger;

  final String severity;

  final String clinicalRisk;

  final String recommendation;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['medication'] = medication;
    json['contraindication_type'] = contraindicationType;
    json['trigger'] = trigger;
    json['severity'] = severity;
    json['clinical_risk'] = clinicalRisk;
    json['recommendation'] = recommendation;
    return json;
  }
}

class DayOfWeekBreakdown {
  const DayOfWeekBreakdown({
    required this.dayName,
    required this.totalExpected,
    required this.totalTaken,
    this.adherenceRate,
  });

  factory DayOfWeekBreakdown.fromJson(Map<String, dynamic> json) => DayOfWeekBreakdown(
        dayName: json['day_name'] as String,
        totalExpected: (json['total_expected'] as num).toInt(),
        totalTaken: (json['total_taken'] as num).toInt(),
        adherenceRate: json['adherence_rate'] == null ? null : (json['adherence_rate'] as num).toDouble(),
      );

  final String dayName;

  final int totalExpected;

  final int totalTaken;

  /// Null when there are no expected doses to divide by. A null rate means "not measurable", NOT zero and NOT 100%: render it as no-data (an em dash, a greyed bar) rather than substituting a number.
  final double? adherenceRate;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['day_name'] = dayName;
    json['total_expected'] = totalExpected;
    json['total_taken'] = totalTaken;
    {
      final value = adherenceRate;
      if (value != null) {
        json['adherence_rate'] = value;
      }
    }
    return json;
  }
}

/// Client request to record dose status. scheduled_at is derived authoritatively on backend.
class DoseLogCreate {
  const DoseLogCreate({
    required this.scheduleId,
    required this.status,
    this.reminderId,
    this.skipReasonCode,
    this.skipReason,
  });

  factory DoseLogCreate.fromJson(Map<String, dynamic> json) => DoseLogCreate(
        scheduleId: (json['schedule_id'] as num).toInt(),
        status: json['status'] as String,
        reminderId: json['reminder_id'] == null ? null : (json['reminder_id'] as num).toInt(),
        skipReasonCode: json['skip_reason_code'] == null ? null : SkipReasonCode.fromWire(json['skip_reason_code'] as String),
        skipReason: json['skip_reason'] == null ? null : json['skip_reason'] as String,
      );

  final int scheduleId;

  final String status;

  final int? reminderId;

  /// Structured reason the patient selected from the fixed list. Trusted, closed vocabulary. Prefer this over free text: the barrier classifier treats it as OBSERVED evidence, whereas a free-text note can only be guessed at and is reported as INFERRED.
  final SkipReasonCode? skipReasonCode;

  /// Optional free-text note from the patient. UNTRUSTED input: it is stored and shown to a clinician as an attributed quotation, and must never be treated as an instruction by any downstream consumer.
  final String? skipReason;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['schedule_id'] = scheduleId;
    json['status'] = status;
    {
      final value = reminderId;
      if (value != null) {
        json['reminder_id'] = value;
      }
    }
    {
      final value = skipReasonCode;
      if (value != null) {
        json['skip_reason_code'] = value.wire;
      }
    }
    {
      final value = skipReason;
      if (value != null) {
        json['skip_reason'] = value;
      }
    }
    return json;
  }
}

class DoseLogResponse {
  const DoseLogResponse({
    required this.id,
    required this.scheduleId,
    required this.patientId,
    required this.scheduledAt,
    required this.status,
    this.reminderId,
    this.confirmedAt,
    this.recordedBy = 'PATIENT',
    this.skipReasonCode,
    this.skipReason,
  });

  factory DoseLogResponse.fromJson(Map<String, dynamic> json) => DoseLogResponse(
        id: (json['id'] as num).toInt(),
        scheduleId: (json['schedule_id'] as num).toInt(),
        patientId: (json['patient_id'] as num).toInt(),
        reminderId: json['reminder_id'] == null ? null : (json['reminder_id'] as num).toInt(),
        scheduledAt: DateTime.parse(json['scheduled_at'] as String),
        status: json['status'] as String,
        confirmedAt: json['confirmed_at'] == null ? null : DateTime.parse(json['confirmed_at'] as String),
        recordedBy: json['recorded_by'] == null ? 'PATIENT' : json['recorded_by'] as String,
        skipReasonCode: json['skip_reason_code'] == null ? null : json['skip_reason_code'] as String,
        skipReason: json['skip_reason'] == null ? null : json['skip_reason'] as String,
      );

  final int id;

  final int scheduleId;

  final int patientId;

  final int? reminderId;

  final DateTime scheduledAt;

  final String status;

  final DateTime? confirmedAt;

  final String recordedBy;

  final String? skipReasonCode;

  final String? skipReason;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['schedule_id'] = scheduleId;
    json['patient_id'] = patientId;
    {
      final value = reminderId;
      if (value != null) {
        json['reminder_id'] = value;
      }
    }
    json['scheduled_at'] = scheduledAt.toIso8601String();
    json['status'] = status;
    {
      final value = confirmedAt;
      if (value != null) {
        json['confirmed_at'] = value.toIso8601String();
      }
    }
    json['recorded_by'] = recordedBy;
    {
      final value = skipReasonCode;
      if (value != null) {
        json['skip_reason_code'] = value;
      }
    }
    {
      final value = skipReason;
      if (value != null) {
        json['skip_reason'] = value;
      }
    }
    return json;
  }
}

class DuplicateTherapyAlertResponse {
  const DuplicateTherapyAlertResponse({
    required this.medications,
    required this.drugClass,
    required this.severity,
    required this.clinicalRisk,
    required this.recommendation,
  });

  factory DuplicateTherapyAlertResponse.fromJson(Map<String, dynamic> json) => DuplicateTherapyAlertResponse(
        medications: (json['medications'] as List<dynamic>).map((e) => e as String).toList(),
        drugClass: json['drug_class'] as String,
        severity: json['severity'] as String,
        clinicalRisk: json['clinical_risk'] as String,
        recommendation: json['recommendation'] as String,
      );

  final List<String> medications;

  final String drugClass;

  final String severity;

  final String clinicalRisk;

  final String recommendation;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['medications'] = medications;
    json['drug_class'] = drugClass;
    json['severity'] = severity;
    json['clinical_risk'] = clinicalRisk;
    json['recommendation'] = recommendation;
    return json;
  }
}

/// Clinician request to correct a mislogged dose event.
class EventCorrectionRequest {
  const EventCorrectionRequest({
    required this.newStatus,
    required this.reason,
  });

  factory EventCorrectionRequest.fromJson(Map<String, dynamic> json) => EventCorrectionRequest(
        newStatus: json['new_status'] as String,
        reason: json['reason'] as String,
      );

  /// The corrected status: TAKEN, SKIPPED, or MISSED.
  final String newStatus;

  /// Mandatory clinical reason for the correction.
  final String reason;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['new_status'] = newStatus;
    json['reason'] = reason;
    return json;
  }
}

/// Confirmation of a dose event correction with audit trail.
class EventCorrectionResponse {
  const EventCorrectionResponse({
    required this.correctionId,
    required this.eventId,
    required this.previousStatus,
    required this.newStatus,
    required this.correctedAt,
    required this.reason,
    this.correctedBy,
  });

  factory EventCorrectionResponse.fromJson(Map<String, dynamic> json) => EventCorrectionResponse(
        correctionId: (json['correction_id'] as num).toInt(),
        eventId: (json['event_id'] as num).toInt(),
        previousStatus: json['previous_status'] as String,
        newStatus: json['new_status'] as String,
        correctedBy: json['corrected_by'] == null ? null : (json['corrected_by'] as num).toInt(),
        correctedAt: json['corrected_at'] as String,
        reason: json['reason'] as String,
      );

  final int correctionId;

  final int eventId;

  final String previousStatus;

  final String newStatus;

  final int? correctedBy;

  final String correctedAt;

  final String reason;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['correction_id'] = correctionId;
    json['event_id'] = eventId;
    json['previous_status'] = previousStatus;
    json['new_status'] = newStatus;
    {
      final value = correctedBy;
      if (value != null) {
        json['corrected_by'] = value;
      }
    }
    json['corrected_at'] = correctedAt;
    json['reason'] = reason;
    return json;
  }
}

/// Narrative components synthesized by the generative model.
/// The LLM ONLY generates these fields. It does not touch safety or adherence arithmetic.
class GenerativeClinicalInsights {
  const GenerativeClinicalInsights({
    this.trend = 'UNKNOWN',
    this.concerningPatterns,
    this.possibleBarriers,
  });

  factory GenerativeClinicalInsights.fromJson(Map<String, dynamic> json) => GenerativeClinicalInsights(
        trend: json['trend'] == null ? null : json['trend'] as String,
        concerningPatterns: json['concerning_patterns'] == null ? null : (json['concerning_patterns'] as List<dynamic>).map((e) => e as String).toList(),
        possibleBarriers: json['possible_barriers'] == null ? null : (json['possible_barriers'] as List<dynamic>).map((e) => BarrierItem.fromJson(e as Map<String, dynamic>)).toList(),
      );

  final String? trend;

  final List<String>? concerningPatterns;

  final List<BarrierItem>? possibleBarriers;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    {
      final value = trend;
      if (value != null) {
        json['trend'] = value;
      }
    }
    {
      final value = concerningPatterns;
      if (value != null) {
        json['concerning_patterns'] = value;
      }
    }
    {
      final value = possibleBarriers;
      if (value != null) {
        json['possible_barriers'] = value.map((e) => e.toJson()).toList();
      }
    }
    return json;
  }
}

class HTTPValidationError {
  const HTTPValidationError({
    this.detail,
  });

  factory HTTPValidationError.fromJson(Map<String, dynamic> json) => HTTPValidationError(
        detail: json['detail'] == null ? null : (json['detail'] as List<dynamic>).map((e) => ValidationError.fromJson(e as Map<String, dynamic>)).toList(),
      );

  final List<ValidationError>? detail;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    {
      final value = detail;
      if (value != null) {
        json['detail'] = value.map((e) => e.toJson()).toList();
      }
    }
    return json;
  }
}

class MedicationCreate {
  const MedicationCreate({
    required this.brandName,
    required this.genericName,
    this.drugClass,
    this.dosageForm,
    this.standardStrength,
    this.foodInteractionNotes,
  });

  factory MedicationCreate.fromJson(Map<String, dynamic> json) => MedicationCreate(
        brandName: json['brand_name'] as String,
        genericName: json['generic_name'] as String,
        drugClass: json['drug_class'] == null ? null : json['drug_class'] as String,
        dosageForm: json['dosage_form'] == null ? null : json['dosage_form'] as String,
        standardStrength: json['standard_strength'] == null ? null : json['standard_strength'] as String,
        foodInteractionNotes: json['food_interaction_notes'] == null ? null : json['food_interaction_notes'] as String,
      );

  final String brandName;

  final String genericName;

  final String? drugClass;

  final String? dosageForm;

  final String? standardStrength;

  final String? foodInteractionNotes;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['brand_name'] = brandName;
    json['generic_name'] = genericName;
    {
      final value = drugClass;
      if (value != null) {
        json['drug_class'] = value;
      }
    }
    {
      final value = dosageForm;
      if (value != null) {
        json['dosage_form'] = value;
      }
    }
    {
      final value = standardStrength;
      if (value != null) {
        json['standard_strength'] = value;
      }
    }
    {
      final value = foodInteractionNotes;
      if (value != null) {
        json['food_interaction_notes'] = value;
      }
    }
    return json;
  }
}

class MedicationInteractionAlertResponse {
  const MedicationInteractionAlertResponse({
    required this.drugA,
    required this.drugB,
    required this.severity,
    required this.mechanism,
    required this.clinicalEffect,
    required this.recommendation,
    required this.source,
  });

  factory MedicationInteractionAlertResponse.fromJson(Map<String, dynamic> json) => MedicationInteractionAlertResponse(
        drugA: json['drug_a'] as String,
        drugB: json['drug_b'] as String,
        severity: json['severity'] as String,
        mechanism: json['mechanism'] as String,
        clinicalEffect: json['clinical_effect'] as String,
        recommendation: json['recommendation'] as String,
        source: json['source'] as String,
      );

  final String drugA;

  final String drugB;

  final String severity;

  final String mechanism;

  final String clinicalEffect;

  final String recommendation;

  final String source;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['drug_a'] = drugA;
    json['drug_b'] = drugB;
    json['severity'] = severity;
    json['mechanism'] = mechanism;
    json['clinical_effect'] = clinicalEffect;
    json['recommendation'] = recommendation;
    json['source'] = source;
    return json;
  }
}

/// What a correction actually changed, reported back to the verifier.
class MedicationReconciliationSummary {
  const MedicationReconciliationSummary({
    required this.unchanged,
    required this.added,
    required this.reactivated,
    required this.discontinued,
    required this.activeTotal,
  });

  factory MedicationReconciliationSummary.fromJson(Map<String, dynamic> json) => MedicationReconciliationSummary(
        unchanged: (json['unchanged'] as num).toInt(),
        added: (json['added'] as num).toInt(),
        reactivated: (json['reactivated'] as num).toInt(),
        discontinued: (json['discontinued'] as num).toInt(),
        activeTotal: (json['active_total'] as num).toInt(),
      );

  final int unchanged;

  final int added;

  final int reactivated;

  final int discontinued;

  final int activeTotal;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['unchanged'] = unchanged;
    json['added'] = added;
    json['reactivated'] = reactivated;
    json['discontinued'] = discontinued;
    json['active_total'] = activeTotal;
    return json;
  }
}

class MedicationResponse {
  const MedicationResponse({
    required this.id,
    required this.brandName,
    required this.genericName,
    required this.createdAt,
    this.drugClass,
    this.dosageForm,
    this.standardStrength,
    this.foodInteractionNotes,
  });

  factory MedicationResponse.fromJson(Map<String, dynamic> json) => MedicationResponse(
        id: (json['id'] as num).toInt(),
        brandName: json['brand_name'] as String,
        genericName: json['generic_name'] as String,
        drugClass: json['drug_class'] == null ? null : json['drug_class'] as String,
        dosageForm: json['dosage_form'] == null ? null : json['dosage_form'] as String,
        standardStrength: json['standard_strength'] == null ? null : json['standard_strength'] as String,
        foodInteractionNotes: json['food_interaction_notes'] == null ? null : json['food_interaction_notes'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final int id;

  final String brandName;

  final String genericName;

  final String? drugClass;

  final String? dosageForm;

  final String? standardStrength;

  final String? foodInteractionNotes;

  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['brand_name'] = brandName;
    json['generic_name'] = genericName;
    {
      final value = drugClass;
      if (value != null) {
        json['drug_class'] = value;
      }
    }
    {
      final value = dosageForm;
      if (value != null) {
        json['dosage_form'] = value;
      }
    }
    {
      final value = standardStrength;
      if (value != null) {
        json['standard_strength'] = value;
      }
    }
    {
      final value = foodInteractionNotes;
      if (value != null) {
        json['food_interaction_notes'] = value;
      }
    }
    json['created_at'] = createdAt.toIso8601String();
    return json;
  }
}

class MedicationUpdate {
  const MedicationUpdate({
    this.brandName,
    this.genericName,
    this.drugClass,
    this.dosageForm,
    this.standardStrength,
    this.foodInteractionNotes,
  });

  factory MedicationUpdate.fromJson(Map<String, dynamic> json) => MedicationUpdate(
        brandName: json['brand_name'] == null ? null : json['brand_name'] as String,
        genericName: json['generic_name'] == null ? null : json['generic_name'] as String,
        drugClass: json['drug_class'] == null ? null : json['drug_class'] as String,
        dosageForm: json['dosage_form'] == null ? null : json['dosage_form'] as String,
        standardStrength: json['standard_strength'] == null ? null : json['standard_strength'] as String,
        foodInteractionNotes: json['food_interaction_notes'] == null ? null : json['food_interaction_notes'] as String,
      );

  final String? brandName;

  final String? genericName;

  final String? drugClass;

  final String? dosageForm;

  final String? standardStrength;

  final String? foodInteractionNotes;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    {
      final value = brandName;
      if (value != null) {
        json['brand_name'] = value;
      }
    }
    {
      final value = genericName;
      if (value != null) {
        json['generic_name'] = value;
      }
    }
    {
      final value = drugClass;
      if (value != null) {
        json['drug_class'] = value;
      }
    }
    {
      final value = dosageForm;
      if (value != null) {
        json['dosage_form'] = value;
      }
    }
    {
      final value = standardStrength;
      if (value != null) {
        json['standard_strength'] = value;
      }
    }
    {
      final value = foodInteractionNotes;
      if (value != null) {
        json['food_interaction_notes'] = value;
      }
    }
    return json;
  }
}

/// Patient-friendly, jargon-free adherence summary and guidance.
class PatientExplanation {
  const PatientExplanation({
    required this.summary,
    required this.whatTheSystemFound,
    required this.whyItMatters,
    required this.whatToDoNext,
    required this.whenToContactCareTeam,
    this.citations,
  });

  factory PatientExplanation.fromJson(Map<String, dynamic> json) => PatientExplanation(
        summary: json['summary'] as String,
        whatTheSystemFound: json['what_the_system_found'] as String,
        whyItMatters: json['why_it_matters'] as String,
        whatToDoNext: json['what_to_do_next'] as String,
        whenToContactCareTeam: json['when_to_contact_care_team'] as String,
        citations: json['citations'] == null ? null : (json['citations'] as List<dynamic>).map((e) => e as String).toList(),
      );

  final String summary;

  final String whatTheSystemFound;

  final String whyItMatters;

  final String whatToDoNext;

  final String whenToContactCareTeam;

  final List<String>? citations;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['summary'] = summary;
    json['what_the_system_found'] = whatTheSystemFound;
    json['why_it_matters'] = whyItMatters;
    json['what_to_do_next'] = whatToDoNext;
    json['when_to_contact_care_team'] = whenToContactCareTeam;
    {
      final value = citations;
      if (value != null) {
        json['citations'] = value;
      }
    }
    return json;
  }
}

class PatientResponse {
  const PatientResponse({
    required this.id,
    required this.userId,
    required this.preferredLanguage,
    required this.timezone,
    required this.createdAt,
    this.emergencyContact,
    this.dateOfBirth,
    this.gender,
    this.bloodGroup,
    this.allergies = const [],
    this.chronicConditions = const [],
    this.name,
    this.email,
  });

  factory PatientResponse.fromJson(Map<String, dynamic> json) => PatientResponse(
        id: (json['id'] as num).toInt(),
        userId: (json['user_id'] as num).toInt(),
        emergencyContact: json['emergency_contact'] == null ? null : json['emergency_contact'] as String,
        dateOfBirth: json['date_of_birth'] == null ? null : DateTime.parse(json['date_of_birth'] as String),
        gender: json['gender'] == null ? null : json['gender'] as String,
        bloodGroup: json['blood_group'] == null ? null : json['blood_group'] as String,
        allergies: json['allergies'] == null ? const [] : (json['allergies'] as List<dynamic>).map((e) => e as String).toList(),
        chronicConditions: json['chronic_conditions'] == null ? const [] : (json['chronic_conditions'] as List<dynamic>).map((e) => e as String).toList(),
        preferredLanguage: json['preferred_language'] as String,
        timezone: json['timezone'] as String,
        name: json['name'] == null ? null : json['name'] as String,
        email: json['email'] == null ? null : json['email'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final int id;

  final int userId;

  final String? emergencyContact;

  final DateTime? dateOfBirth;

  final String? gender;

  final String? bloodGroup;

  final List<String> allergies;

  final List<String> chronicConditions;

  final String preferredLanguage;

  final String timezone;

  final String? name;

  final String? email;

  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['user_id'] = userId;
    {
      final value = emergencyContact;
      if (value != null) {
        json['emergency_contact'] = value;
      }
    }
    {
      final value = dateOfBirth;
      if (value != null) {
        json['date_of_birth'] = _encodeDate(value);
      }
    }
    {
      final value = gender;
      if (value != null) {
        json['gender'] = value;
      }
    }
    {
      final value = bloodGroup;
      if (value != null) {
        json['blood_group'] = value;
      }
    }
    json['allergies'] = allergies;
    json['chronic_conditions'] = chronicConditions;
    json['preferred_language'] = preferredLanguage;
    json['timezone'] = timezone;
    {
      final value = name;
      if (value != null) {
        json['name'] = value;
      }
    }
    {
      final value = email;
      if (value != null) {
        json['email'] = value;
      }
    }
    json['created_at'] = createdAt.toIso8601String();
    return json;
  }
}

class PatientUpdate {
  const PatientUpdate({
    this.emergencyContact,
    this.dateOfBirth,
    this.gender,
    this.bloodGroup,
    this.allergies,
    this.chronicConditions,
    this.preferredLanguage,
    this.timezone,
  });

  factory PatientUpdate.fromJson(Map<String, dynamic> json) => PatientUpdate(
        emergencyContact: json['emergency_contact'] == null ? null : json['emergency_contact'] as String,
        dateOfBirth: json['date_of_birth'] == null ? null : DateTime.parse(json['date_of_birth'] as String),
        gender: json['gender'] == null ? null : json['gender'] as String,
        bloodGroup: json['blood_group'] == null ? null : json['blood_group'] as String,
        allergies: json['allergies'] == null ? null : (json['allergies'] as List<dynamic>).map((e) => e as String).toList(),
        chronicConditions: json['chronic_conditions'] == null ? null : (json['chronic_conditions'] as List<dynamic>).map((e) => e as String).toList(),
        preferredLanguage: json['preferred_language'] == null ? null : json['preferred_language'] as String,
        timezone: json['timezone'] == null ? null : json['timezone'] as String,
      );

  final String? emergencyContact;

  final DateTime? dateOfBirth;

  final String? gender;

  final String? bloodGroup;

  final List<String>? allergies;

  final List<String>? chronicConditions;

  final String? preferredLanguage;

  final String? timezone;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    {
      final value = emergencyContact;
      if (value != null) {
        json['emergency_contact'] = value;
      }
    }
    {
      final value = dateOfBirth;
      if (value != null) {
        json['date_of_birth'] = _encodeDate(value);
      }
    }
    {
      final value = gender;
      if (value != null) {
        json['gender'] = value;
      }
    }
    {
      final value = bloodGroup;
      if (value != null) {
        json['blood_group'] = value;
      }
    }
    {
      final value = allergies;
      if (value != null) {
        json['allergies'] = value;
      }
    }
    {
      final value = chronicConditions;
      if (value != null) {
        json['chronic_conditions'] = value;
      }
    }
    {
      final value = preferredLanguage;
      if (value != null) {
        json['preferred_language'] = value;
      }
    }
    {
      final value = timezone;
      if (value != null) {
        json['timezone'] = value;
      }
    }
    return json;
  }
}

class PrescribedMedicationCreate {
  const PrescribedMedicationCreate({
    required this.medicineName,
    required this.frequency,
    this.strength,
    this.dose,
    this.durationDays,
    this.instructions,
  });

  factory PrescribedMedicationCreate.fromJson(Map<String, dynamic> json) => PrescribedMedicationCreate(
        medicineName: json['medicine_name'] as String,
        strength: json['strength'] == null ? null : json['strength'] as String,
        dose: json['dose'] == null ? null : json['dose'] as String,
        frequency: json['frequency'] as String,
        durationDays: json['duration_days'] == null ? null : (json['duration_days'] as num).toInt(),
        instructions: json['instructions'] == null ? null : json['instructions'] as String,
      );

  final String medicineName;

  final String? strength;

  final String? dose;

  final String frequency;

  final int? durationDays;

  final String? instructions;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['medicine_name'] = medicineName;
    {
      final value = strength;
      if (value != null) {
        json['strength'] = value;
      }
    }
    {
      final value = dose;
      if (value != null) {
        json['dose'] = value;
      }
    }
    json['frequency'] = frequency;
    {
      final value = durationDays;
      if (value != null) {
        json['duration_days'] = value;
      }
    }
    {
      final value = instructions;
      if (value != null) {
        json['instructions'] = value;
      }
    }
    return json;
  }
}

class PrescribedMedicationResponse {
  const PrescribedMedicationResponse({
    required this.id,
    required this.prescriptionId,
    required this.patientId,
    required this.medicineName,
    required this.frequency,
    required this.isActive,
    this.strength,
    this.dose,
    this.durationDays,
    this.instructions,
    this.medicationId,
  });

  factory PrescribedMedicationResponse.fromJson(Map<String, dynamic> json) => PrescribedMedicationResponse(
        id: (json['id'] as num).toInt(),
        prescriptionId: (json['prescription_id'] as num).toInt(),
        patientId: (json['patient_id'] as num).toInt(),
        medicineName: json['medicine_name'] as String,
        strength: json['strength'] == null ? null : json['strength'] as String,
        dose: json['dose'] == null ? null : json['dose'] as String,
        frequency: json['frequency'] as String,
        durationDays: json['duration_days'] == null ? null : (json['duration_days'] as num).toInt(),
        instructions: json['instructions'] == null ? null : json['instructions'] as String,
        medicationId: json['medication_id'] == null ? null : (json['medication_id'] as num).toInt(),
        isActive: json['is_active'] as bool,
      );

  final int id;

  final int prescriptionId;

  final int patientId;

  final String medicineName;

  final String? strength;

  final String? dose;

  final String frequency;

  final int? durationDays;

  final String? instructions;

  final int? medicationId;

  final bool isActive;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['prescription_id'] = prescriptionId;
    json['patient_id'] = patientId;
    json['medicine_name'] = medicineName;
    {
      final value = strength;
      if (value != null) {
        json['strength'] = value;
      }
    }
    {
      final value = dose;
      if (value != null) {
        json['dose'] = value;
      }
    }
    json['frequency'] = frequency;
    {
      final value = durationDays;
      if (value != null) {
        json['duration_days'] = value;
      }
    }
    {
      final value = instructions;
      if (value != null) {
        json['instructions'] = value;
      }
    }
    {
      final value = medicationId;
      if (value != null) {
        json['medication_id'] = value;
      }
    }
    json['is_active'] = isActive;
    return json;
  }
}

class PrescriptionCreate {
  const PrescriptionCreate({
    required this.prescriptionDate,
    required this.medications,
    this.doctorName,
    this.clinicName,
  });

  factory PrescriptionCreate.fromJson(Map<String, dynamic> json) => PrescriptionCreate(
        doctorName: json['doctor_name'] == null ? null : json['doctor_name'] as String,
        clinicName: json['clinic_name'] == null ? null : json['clinic_name'] as String,
        prescriptionDate: DateTime.parse(json['prescription_date'] as String),
        medications: (json['medications'] as List<dynamic>).map((e) => PrescribedMedicationCreate.fromJson(e as Map<String, dynamic>)).toList(),
      );

  final String? doctorName;

  final String? clinicName;

  final DateTime prescriptionDate;

  final List<PrescribedMedicationCreate> medications;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    {
      final value = doctorName;
      if (value != null) {
        json['doctor_name'] = value;
      }
    }
    {
      final value = clinicName;
      if (value != null) {
        json['clinic_name'] = value;
      }
    }
    json['prescription_date'] = _encodeDate(prescriptionDate);
    json['medications'] = medications.map((e) => e.toJson()).toList();
    return json;
  }
}

class PrescriptionResponse {
  const PrescriptionResponse({
    required this.id,
    required this.patientId,
    required this.prescriptionDate,
    required this.verificationStatus,
    required this.createdAt,
    this.doctorName,
    this.clinicName,
    this.imageUrl,
    this.verifiedBy,
    this.verifiedAt,
    this.medications = const [],
  });

  factory PrescriptionResponse.fromJson(Map<String, dynamic> json) => PrescriptionResponse(
        id: (json['id'] as num).toInt(),
        patientId: (json['patient_id'] as num).toInt(),
        doctorName: json['doctor_name'] == null ? null : json['doctor_name'] as String,
        clinicName: json['clinic_name'] == null ? null : json['clinic_name'] as String,
        prescriptionDate: DateTime.parse(json['prescription_date'] as String),
        imageUrl: json['image_url'] == null ? null : json['image_url'] as String,
        verificationStatus: json['verification_status'] as String,
        verifiedBy: json['verified_by'] == null ? null : (json['verified_by'] as num).toInt(),
        verifiedAt: json['verified_at'] == null ? null : DateTime.parse(json['verified_at'] as String),
        createdAt: DateTime.parse(json['created_at'] as String),
        medications: json['medications'] == null ? const [] : (json['medications'] as List<dynamic>).map((e) => PrescribedMedicationResponse.fromJson(e as Map<String, dynamic>)).toList(),
      );

  final int id;

  final int patientId;

  final String? doctorName;

  final String? clinicName;

  final DateTime prescriptionDate;

  final String? imageUrl;

  final String verificationStatus;

  final int? verifiedBy;

  final DateTime? verifiedAt;

  final DateTime createdAt;

  final List<PrescribedMedicationResponse> medications;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['patient_id'] = patientId;
    {
      final value = doctorName;
      if (value != null) {
        json['doctor_name'] = value;
      }
    }
    {
      final value = clinicName;
      if (value != null) {
        json['clinic_name'] = value;
      }
    }
    json['prescription_date'] = _encodeDate(prescriptionDate);
    {
      final value = imageUrl;
      if (value != null) {
        json['image_url'] = value;
      }
    }
    json['verification_status'] = verificationStatus;
    {
      final value = verifiedBy;
      if (value != null) {
        json['verified_by'] = value;
      }
    }
    {
      final value = verifiedAt;
      if (value != null) {
        json['verified_at'] = value.toIso8601String();
      }
    }
    json['created_at'] = createdAt.toIso8601String();
    json['medications'] = medications.map((e) => e.toJson()).toList();
    return json;
  }
}

class PrescriptionVerify {
  const PrescriptionVerify({
    required this.verified,
    this.corrections,
  });

  factory PrescriptionVerify.fromJson(Map<String, dynamic> json) => PrescriptionVerify(
        verified: json['verified'] as bool,
        corrections: json['corrections'] == null ? null : (json['corrections'] as List<dynamic>).map((e) => PrescribedMedicationCreate.fromJson(e as Map<String, dynamic>)).toList(),
      );

  final bool verified;

  final List<PrescribedMedicationCreate>? corrections;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['verified'] = verified;
    {
      final value = corrections;
      if (value != null) {
        json['corrections'] = value.map((e) => e.toJson()).toList();
      }
    }
    return json;
  }
}

/// Verify response: the prescription plus scheduling and correction summaries.
///
/// The scheduling summary matters because "verified" alone hides useful facts —
/// notably that an as-needed medication was deliberately given no dose times, so
/// the clinician is not left wondering why no reminders appeared for it. Null
/// when the prescription was rejected.
///
/// The reconciliation summary makes a correction's effect visible: how many
/// lines were kept, added, brought back, and discontinued. Null when the request
/// carried no corrections.
class PrescriptionVerifyResponse {
  const PrescriptionVerifyResponse({
    required this.id,
    required this.patientId,
    required this.prescriptionDate,
    required this.verificationStatus,
    required this.createdAt,
    this.doctorName,
    this.clinicName,
    this.imageUrl,
    this.verifiedBy,
    this.verifiedAt,
    this.medications = const [],
    this.scheduling,
    this.reconciliation,
  });

  factory PrescriptionVerifyResponse.fromJson(Map<String, dynamic> json) => PrescriptionVerifyResponse(
        id: (json['id'] as num).toInt(),
        patientId: (json['patient_id'] as num).toInt(),
        doctorName: json['doctor_name'] == null ? null : json['doctor_name'] as String,
        clinicName: json['clinic_name'] == null ? null : json['clinic_name'] as String,
        prescriptionDate: DateTime.parse(json['prescription_date'] as String),
        imageUrl: json['image_url'] == null ? null : json['image_url'] as String,
        verificationStatus: json['verification_status'] as String,
        verifiedBy: json['verified_by'] == null ? null : (json['verified_by'] as num).toInt(),
        verifiedAt: json['verified_at'] == null ? null : DateTime.parse(json['verified_at'] as String),
        createdAt: DateTime.parse(json['created_at'] as String),
        medications: json['medications'] == null ? const [] : (json['medications'] as List<dynamic>).map((e) => PrescribedMedicationResponse.fromJson(e as Map<String, dynamic>)).toList(),
        scheduling: json['scheduling'] == null ? null : ScheduleGenerationSummary.fromJson(json['scheduling'] as Map<String, dynamic>),
        reconciliation: json['reconciliation'] == null ? null : MedicationReconciliationSummary.fromJson(json['reconciliation'] as Map<String, dynamic>),
      );

  final int id;

  final int patientId;

  final String? doctorName;

  final String? clinicName;

  final DateTime prescriptionDate;

  final String? imageUrl;

  final String verificationStatus;

  final int? verifiedBy;

  final DateTime? verifiedAt;

  final DateTime createdAt;

  final List<PrescribedMedicationResponse> medications;

  final ScheduleGenerationSummary? scheduling;

  final MedicationReconciliationSummary? reconciliation;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['patient_id'] = patientId;
    {
      final value = doctorName;
      if (value != null) {
        json['doctor_name'] = value;
      }
    }
    {
      final value = clinicName;
      if (value != null) {
        json['clinic_name'] = value;
      }
    }
    json['prescription_date'] = _encodeDate(prescriptionDate);
    {
      final value = imageUrl;
      if (value != null) {
        json['image_url'] = value;
      }
    }
    json['verification_status'] = verificationStatus;
    {
      final value = verifiedBy;
      if (value != null) {
        json['verified_by'] = value;
      }
    }
    {
      final value = verifiedAt;
      if (value != null) {
        json['verified_at'] = value.toIso8601String();
      }
    }
    json['created_at'] = createdAt.toIso8601String();
    json['medications'] = medications.map((e) => e.toJson()).toList();
    {
      final value = scheduling;
      if (value != null) {
        json['scheduling'] = value.toJson();
      }
    }
    {
      final value = reconciliation;
      if (value != null) {
        json['reconciliation'] = value.toJson();
      }
    }
    return json;
  }
}

class SafetyAssessmentResponse {
  const SafetyAssessmentResponse({
    required this.patientId,
    required this.evaluatedAt,
    required this.riskLevel,
    required this.requiresHumanReview,
    required this.recommendedAction,
    this.medicationInteractions = const [],
    this.contraindications = const [],
    this.duplicateTherapies = const [],
    this.adherenceRisks = const [],
    this.evidence = const [],
  });

  factory SafetyAssessmentResponse.fromJson(Map<String, dynamic> json) => SafetyAssessmentResponse(
        patientId: (json['patient_id'] as num).toInt(),
        evaluatedAt: DateTime.parse(json['evaluated_at'] as String),
        riskLevel: json['risk_level'] as String,
        requiresHumanReview: json['requires_human_review'] as bool,
        recommendedAction: json['recommended_action'] as String,
        medicationInteractions: json['medication_interactions'] == null ? const [] : (json['medication_interactions'] as List<dynamic>).map((e) => MedicationInteractionAlertResponse.fromJson(e as Map<String, dynamic>)).toList(),
        contraindications: json['contraindications'] == null ? const [] : (json['contraindications'] as List<dynamic>).map((e) => ContraindicationAlertResponse.fromJson(e as Map<String, dynamic>)).toList(),
        duplicateTherapies: json['duplicate_therapies'] == null ? const [] : (json['duplicate_therapies'] as List<dynamic>).map((e) => DuplicateTherapyAlertResponse.fromJson(e as Map<String, dynamic>)).toList(),
        adherenceRisks: json['adherence_risks'] == null ? const [] : (json['adherence_risks'] as List<dynamic>).map((e) => AdherenceSafetyAlertResponse.fromJson(e as Map<String, dynamic>)).toList(),
        evidence: json['evidence'] == null ? const [] : (json['evidence'] as List<dynamic>).map((e) => SafetyEvidenceResponse.fromJson(e as Map<String, dynamic>)).toList(),
      );

  final int patientId;

  final DateTime evaluatedAt;

  final String riskLevel;

  final bool requiresHumanReview;

  final String recommendedAction;

  final List<MedicationInteractionAlertResponse> medicationInteractions;

  final List<ContraindicationAlertResponse> contraindications;

  final List<DuplicateTherapyAlertResponse> duplicateTherapies;

  final List<AdherenceSafetyAlertResponse> adherenceRisks;

  final List<SafetyEvidenceResponse> evidence;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['patient_id'] = patientId;
    json['evaluated_at'] = evaluatedAt.toIso8601String();
    json['risk_level'] = riskLevel;
    json['requires_human_review'] = requiresHumanReview;
    json['recommended_action'] = recommendedAction;
    json['medication_interactions'] = medicationInteractions.map((e) => e.toJson()).toList();
    json['contraindications'] = contraindications.map((e) => e.toJson()).toList();
    json['duplicate_therapies'] = duplicateTherapies.map((e) => e.toJson()).toList();
    json['adherence_risks'] = adherenceRisks.map((e) => e.toJson()).toList();
    json['evidence'] = evidence.map((e) => e.toJson()).toList();
    return json;
  }
}

class SafetyEvidenceResponse {
  const SafetyEvidenceResponse({
    required this.category,
    required this.finding,
    required this.severity,
    required this.referenceSource,
  });

  factory SafetyEvidenceResponse.fromJson(Map<String, dynamic> json) => SafetyEvidenceResponse(
        category: json['category'] as String,
        finding: json['finding'] as String,
        severity: json['severity'] as String,
        referenceSource: json['reference_source'] as String,
      );

  final String category;

  final String finding;

  final String severity;

  final String referenceSource;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['category'] = category;
    json['finding'] = finding;
    json['severity'] = severity;
    json['reference_source'] = referenceSource;
    return json;
  }
}

/// What schedule generation actually did, reported back to the verifier.
class ScheduleGenerationSummary {
  const ScheduleGenerationSummary({
    required this.created,
    required this.reactivated,
    required this.deactivated,
    required this.unchanged,
    required this.activeTotal,
    this.asNeeded = const [],
  });

  factory ScheduleGenerationSummary.fromJson(Map<String, dynamic> json) => ScheduleGenerationSummary(
        created: (json['created'] as num).toInt(),
        reactivated: (json['reactivated'] as num).toInt(),
        deactivated: (json['deactivated'] as num).toInt(),
        unchanged: (json['unchanged'] as num).toInt(),
        activeTotal: (json['active_total'] as num).toInt(),
        asNeeded: json['as_needed'] == null ? const [] : (json['as_needed'] as List<dynamic>).map((e) => e as String).toList(),
      );

  final int created;

  final int reactivated;

  final int deactivated;

  final int unchanged;

  final int activeTotal;

  final List<String> asNeeded;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['created'] = created;
    json['reactivated'] = reactivated;
    json['deactivated'] = deactivated;
    json['unchanged'] = unchanged;
    json['active_total'] = activeTotal;
    json['as_needed'] = asNeeded;
    return json;
  }
}

/// One historical snapshot of a schedule's state.
class ScheduleVersionResponse {
  const ScheduleVersionResponse({
    required this.id,
    required this.scheduleId,
    required this.versionNumber,
    required this.validFrom,
    required this.scheduleData,
    this.validTo,
  });

  factory ScheduleVersionResponse.fromJson(Map<String, dynamic> json) => ScheduleVersionResponse(
        id: (json['id'] as num).toInt(),
        scheduleId: (json['schedule_id'] as num).toInt(),
        versionNumber: (json['version_number'] as num).toInt(),
        validFrom: json['valid_from'] as String,
        validTo: json['valid_to'] == null ? null : json['valid_to'] as String,
        scheduleData: json['schedule_data'] as Map<String, dynamic>,
      );

  final int id;

  final int scheduleId;

  final int versionNumber;

  final String validFrom;

  final String? validTo;

  final Map<String, dynamic> scheduleData;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['schedule_id'] = scheduleId;
    json['version_number'] = versionNumber;
    json['valid_from'] = validFrom;
    {
      final value = validTo;
      if (value != null) {
        json['valid_to'] = value;
      }
    }
    json['schedule_data'] = scheduleData;
    return json;
  }
}

class TimeSlotBreakdown {
  const TimeSlotBreakdown({
    required this.totalExpected,
    required this.totalTaken,
    required this.totalMissed,
    required this.totalSkipped,
    this.adherenceRate,
  });

  factory TimeSlotBreakdown.fromJson(Map<String, dynamic> json) => TimeSlotBreakdown(
        totalExpected: (json['total_expected'] as num).toInt(),
        totalTaken: (json['total_taken'] as num).toInt(),
        totalMissed: (json['total_missed'] as num).toInt(),
        totalSkipped: (json['total_skipped'] as num).toInt(),
        adherenceRate: json['adherence_rate'] == null ? null : (json['adherence_rate'] as num).toDouble(),
      );

  final int totalExpected;

  final int totalTaken;

  final int totalMissed;

  final int totalSkipped;

  /// Null when there are no expected doses to divide by. A null rate means "not measurable", NOT zero and NOT 100%: render it as no-data (an em dash, a greyed bar) rather than substituting a number.
  final double? adherenceRate;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['total_expected'] = totalExpected;
    json['total_taken'] = totalTaken;
    json['total_missed'] = totalMissed;
    json['total_skipped'] = totalSkipped;
    {
      final value = adherenceRate;
      if (value != null) {
        json['adherence_rate'] = value;
      }
    }
    return json;
  }
}

/// One scheduled dose on the patient's local calendar day today.
class TodayDoseResponse {
  const TodayDoseResponse({
    required this.scheduleId,
    required this.medicineName,
    required this.scheduledAt,
    required this.scheduledLocalTime,
    required this.status,
    required this.isDue,
    this.eventId,
    this.reminderId,
    this.strength,
    this.dose,
    this.instructions,
    this.relationToMeal,
    this.confirmedAt,
    this.skipReasonCode,
    this.skipReason,
  });

  factory TodayDoseResponse.fromJson(Map<String, dynamic> json) => TodayDoseResponse(
        scheduleId: (json['schedule_id'] as num).toInt(),
        eventId: json['event_id'] == null ? null : (json['event_id'] as num).toInt(),
        reminderId: json['reminder_id'] == null ? null : (json['reminder_id'] as num).toInt(),
        medicineName: json['medicine_name'] as String,
        strength: json['strength'] == null ? null : json['strength'] as String,
        dose: json['dose'] == null ? null : json['dose'] as String,
        instructions: json['instructions'] == null ? null : json['instructions'] as String,
        relationToMeal: json['relation_to_meal'] == null ? null : json['relation_to_meal'] as String,
        scheduledAt: DateTime.parse(json['scheduled_at'] as String),
        scheduledLocalTime: json['scheduled_local_time'] as String,
        status: json['status'] as String,
        confirmedAt: json['confirmed_at'] == null ? null : DateTime.parse(json['confirmed_at'] as String),
        skipReasonCode: json['skip_reason_code'] == null ? null : json['skip_reason_code'] as String,
        skipReason: json['skip_reason'] == null ? null : json['skip_reason'] as String,
        isDue: json['is_due'] as bool,
      );

  /// Post this back to /adherence/log to record the dose. The backend re-derives the scheduled instant from it and never trusts a client-supplied timestamp.
  final int scheduleId;

  /// The MedicationEvent row, if one exists yet. Null means nothing has happened to this dose — not that data is missing.
  final int? eventId;

  /// The reminder for this exact slot, if one has been created. Pass it through when logging so the reminder is acknowledged rather than left to expire as MISSED.
  final int? reminderId;

  final String medicineName;

  final String? strength;

  final String? dose;

  final String? instructions;

  /// BEFORE_MEAL / AFTER_MEAL / WITH_MEAL / EMPTY_STOMACH, or null.
  final String? relationToMeal;

  /// Authoritative UTC instant for this dose.
  final DateTime scheduledAt;

  /// 24-hour HH:MM wall-clock time in the patient's timezone, for display.
  final String scheduledLocalTime;

  /// PENDING / TAKEN / SKIPPED / MISSED / SNOOZED. PENDING = not yet logged.
  final String status;

  final DateTime? confirmedAt;

  /// Trusted closed-vocabulary reason the patient selected. Safe to render anywhere.
  final String? skipReasonCode;

  /// UNTRUSTED free text the patient typed. Display it as an attributed quotation only. Never concatenate it into an instruction, a prompt, or any string a machine will interpret.
  final String? skipReason;

  /// True once the scheduled instant has passed. A dose later in the day is not actionable yet.
  final bool isDue;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['schedule_id'] = scheduleId;
    {
      final value = eventId;
      if (value != null) {
        json['event_id'] = value;
      }
    }
    {
      final value = reminderId;
      if (value != null) {
        json['reminder_id'] = value;
      }
    }
    json['medicine_name'] = medicineName;
    {
      final value = strength;
      if (value != null) {
        json['strength'] = value;
      }
    }
    {
      final value = dose;
      if (value != null) {
        json['dose'] = value;
      }
    }
    {
      final value = instructions;
      if (value != null) {
        json['instructions'] = value;
      }
    }
    {
      final value = relationToMeal;
      if (value != null) {
        json['relation_to_meal'] = value;
      }
    }
    json['scheduled_at'] = scheduledAt.toIso8601String();
    json['scheduled_local_time'] = scheduledLocalTime;
    json['status'] = status;
    {
      final value = confirmedAt;
      if (value != null) {
        json['confirmed_at'] = value.toIso8601String();
      }
    }
    {
      final value = skipReasonCode;
      if (value != null) {
        json['skip_reason_code'] = value;
      }
    }
    {
      final value = skipReason;
      if (value != null) {
        json['skip_reason'] = value;
      }
    }
    json['is_due'] = isDue;
    return json;
  }
}

/// The patient's full dose list for today, chronological.
class TodayScheduleResponse {
  const TodayScheduleResponse({
    required this.patientId,
    required this.localDate,
    required this.timezone,
    required this.doses,
    required this.totalDoses,
    required this.dosesTaken,
    required this.dosesRemaining,
  });

  factory TodayScheduleResponse.fromJson(Map<String, dynamic> json) => TodayScheduleResponse(
        patientId: (json['patient_id'] as num).toInt(),
        localDate: json['local_date'] as String,
        timezone: json['timezone'] as String,
        doses: (json['doses'] as List<dynamic>).map((e) => TodayDoseResponse.fromJson(e as Map<String, dynamic>)).toList(),
        totalDoses: (json['total_doses'] as num).toInt(),
        dosesTaken: (json['doses_taken'] as num).toInt(),
        dosesRemaining: (json['doses_remaining'] as num).toInt(),
      );

  final int patientId;

  /// The patient's local calendar date the list was built for (YYYY-MM-DD).
  final String localDate;

  final String timezone;

  final List<TodayDoseResponse> doses;

  final int totalDoses;

  final int dosesTaken;

  /// Doses not yet logged, whether or not their time has passed.
  final int dosesRemaining;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['patient_id'] = patientId;
    json['local_date'] = localDate;
    json['timezone'] = timezone;
    json['doses'] = doses.map((e) => e.toJson()).toList();
    json['total_doses'] = totalDoses;
    json['doses_taken'] = dosesTaken;
    json['doses_remaining'] = dosesRemaining;
    return json;
  }
}

class TokenRefresh {
  const TokenRefresh({
    required this.refreshToken,
  });

  factory TokenRefresh.fromJson(Map<String, dynamic> json) => TokenRefresh(
        refreshToken: json['refresh_token'] as String,
      );

  final String refreshToken;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['refresh_token'] = refreshToken;
    return json;
  }
}

class TokenResponse {
  const TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
  });

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String,
        tokenType: json['token_type'] == null ? 'bearer' : json['token_type'] as String,
      );

  final String accessToken;

  final String refreshToken;

  final String tokenType;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['access_token'] = accessToken;
    json['refresh_token'] = refreshToken;
    json['token_type'] = tokenType;
    return json;
  }
}

/// Public self-service registration. Creates a PATIENT, and can create nothing else.
///
/// There is deliberately no ``role`` field. It was removed rather than validated,
/// because the two are not equivalent: a rejected-if-not-PATIENT check still
/// publishes ``role`` in the OpenAPI schema, still advertises the enum of roles that
/// exist, and still leaves one edit away from being writable again. An absent field
/// cannot be smuggled through, cannot be forgotten in a refactor, and does not tell
/// an anonymous caller that ADMIN is a thing this system has.
///
/// Privileged accounts are created by ``POST /admin/users``, which requires an
/// authenticated ADMIN. See :class:`AdminUserCreate`.
class UserRegister {
  const UserRegister({
    required this.name,
    required this.email,
    required this.password,
    this.phone,
    this.timezone,
  });

  factory UserRegister.fromJson(Map<String, dynamic> json) => UserRegister(
        name: json['name'] as String,
        email: json['email'] as String,
        password: json['password'] as String,
        phone: json['phone'] == null ? null : json['phone'] as String,
        timezone: json['timezone'] == null ? null : json['timezone'] as String,
      );

  final String name;

  final String email;

  /// Between 8 and 128 characters. No character-class requirements.
  final String password;

  final String? phone;

  /// IANA timezone name, e.g. 'Asia/Kolkata'
  final String? timezone;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['name'] = name;
    json['email'] = email;
    json['password'] = password;
    {
      final value = phone;
      if (value != null) {
        json['phone'] = value;
      }
    }
    {
      final value = timezone;
      if (value != null) {
        json['timezone'] = value;
      }
    }
    return json;
  }
}

class UserResponse {
  const UserResponse({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    required this.isActive,
    required this.createdAt,
    this.phone,
  });

  factory UserResponse.fromJson(Map<String, dynamic> json) => UserResponse(
        id: (json['id'] as num).toInt(),
        name: json['name'] as String,
        email: json['email'] as String,
        phone: json['phone'] == null ? null : json['phone'] as String,
        role: json['role'] as String,
        isActive: json['is_active'] as bool,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final int id;

  final String name;

  final String email;

  final String? phone;

  final String role;

  final bool isActive;

  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['id'] = id;
    json['name'] = name;
    json['email'] = email;
    {
      final value = phone;
      if (value != null) {
        json['phone'] = value;
      }
    }
    json['role'] = role;
    json['is_active'] = isActive;
    json['created_at'] = createdAt.toIso8601String();
    return json;
  }
}

class ValidationError {
  const ValidationError({
    required this.loc,
    required this.msg,
    required this.type,
    this.input,
    this.ctx,
  });

  factory ValidationError.fromJson(Map<String, dynamic> json) => ValidationError(
        loc: (json['loc'] as List<dynamic>).toList(),
        msg: json['msg'] as String,
        type: json['type'] as String,
        input: json['input'],
        ctx: json['ctx'] == null ? null : json['ctx'] as Map<String, dynamic>,
      );

  final List<dynamic> loc;

  final String msg;

  final String type;

  final dynamic input;

  final Map<String, dynamic>? ctx;

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{};
    json['loc'] = loc;
    json['msg'] = msg;
    json['type'] = type;
    {
      final value = input;
      if (value != null) {
        json['input'] = value;
      }
    }
    {
      final value = ctx;
      if (value != null) {
        json['ctx'] = value;
      }
    }
    return json;
  }
}

