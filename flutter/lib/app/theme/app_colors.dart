import 'package:flutter/material.dart';

/// Colour tokens.
///
/// No design export exists in the repository, so these are a defensible clinical
/// default rather than a reproduction of one: a calm blue-grey base, warm accents
/// reserved for action, and status colours chosen for contrast rather than
/// prettiness. Replace the values when a real export arrives; the token *names* are
/// the contract the widgets depend on.
///
/// Two rules the values enforce and that should survive any restyle:
///
/// - **Status is never encoded by colour alone.** Every status token has a paired
///   label and icon at the widget level. Roughly 1 in 12 men has a red-green
///   deficiency, and "taken vs missed" is not a distinction to lose.
/// - **The three trust tiers are visually distinct and consistently applied.** See
///   [deterministicFinding], [verifiedEvidence] and [aiAssisted].
class AppColors {
  const AppColors._();

  // --- base ---
  static const Color primary = Color(0xFF1B5E8C);
  static const Color primaryDark = Color(0xFF12405F);
  static const Color primaryLight = Color(0xFFE3F0F8);
  static const Color accent = Color(0xFF0E8A7A);

  static const Color background = Color(0xFFF7F9FB);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceMuted = Color(0xFFEFF3F7);
  static const Color surfaceVariant = Color(0xFFEFF3F7);
  static const Color outlineLight = Color(0xFFE2E8F0);
  static const Color border = Color(0xFFD6DEE6);

  static const Color textPrimary = Color(0xFF15242E);
  static const Color textSecondary = Color(0xFF526474);
  static const Color textOnPrimary = Color(0xFFFFFFFF);
  static const Color textDisabled = Color(0xFF93A3B0);

  // --- operational failure ---
  // For things the *software* got wrong or cannot do: a request that failed, a feature
  // that is not connected yet. Separate from both the status and trust-tier families on
  // purpose. A dropped network call is not a clinical finding, and dressing it in
  // [deterministicFinding] red would give an outage the visual authority of a rules
  // engine result; borrowing [statusMissed] would imply something about a dose.
  static const Color danger = Color(0xFF9A2A2A);
  static const Color dangerSurface = Color(0xFFFBEEEE);

  // --- dose status ---
  // Matches MedicationEventStatus on the backend: PENDING / TAKEN / SKIPPED /
  // MISSED / SNOOZED. A status the client does not recognise renders in
  // [statusUnknown] rather than defaulting to something reassuring.
  static const Color statusPending = Color(0xFF4A6D85);
  static const Color statusTaken = Color(0xFF1E7A4D);
  static const Color statusSkipped = Color(0xFFB07206);
  static const Color statusMissed = Color(0xFFB3261E);
  static const Color statusSnoozed = Color(0xFF6A5AA8);
  static const Color statusUnknown = Color(0xFF6B7A87);

  // --- risk level ---
  // The backend's SafetyAssessment.risk_level vocabulary, exactly.
  static const Color riskLow = Color(0xFF1E7A4D);
  static const Color riskModerate = Color(0xFFB07206);
  static const Color riskHigh = Color(0xFFC8500F);
  static const Color riskCritical = Color(0xFF8E1116);

  // --- trust tiers ---
  // These three exist so the provenance separation the backend maintains cannot be
  // flattened by the UI. A clinician has to be able to tell, at a glance and
  // without reading, which of three very different things they are looking at:
  //
  //   deterministicFinding — a rules-engine output. Reproducible, auditable.
  //   verifiedEvidence     — retrieved from the clinical knowledge base, cited.
  //   aiAssisted           — generated. Nothing in this codebase produces this yet.
  //
  // Never reuse one tier's colour for another tier's surface.
  static const Color deterministicFinding = Color(0xFF8E1116);
  static const Color deterministicFindingSurface = Color(0xFFFDECEC);
  static const Color verifiedEvidence = Color(0xFF15558A);
  static const Color verifiedEvidenceSurface = Color(0xFFEAF2FB);

  /// Deliberately unlike the other two: generated text must not borrow the visual
  /// authority of a deterministic finding or a cited source.
  static const Color aiAssisted = Color(0xFF5B4B9E);
  static const Color aiAssistedSurface = Color(0xFFF2EFFB);
}
