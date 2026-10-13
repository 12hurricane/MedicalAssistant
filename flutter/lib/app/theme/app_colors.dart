import 'package:flutter/material.dart';

/// Colour tokens.
///
/// Updated for Premium Dark UI Design.
/// A deep slate base provides a sophisticated modern feel, while maintaining
/// strict clinical safety constraints (accessible contrast against dark surfaces,
/// distinct status colors, and separate trust tiers).
///
/// Two rules the values enforce and that should survive any restyle:
///
/// - **Status is never encoded by colour alone.** Every status token has a paired
///   label and icon at the widget level.
/// - **The three trust tiers are visually distinct and consistently applied.** See
///   [deterministicFinding], [verifiedEvidence] and [aiAssisted].
class AppColors {
  const AppColors._();

  // --- base ---
  // Premium dark mode uses Slate/Dark Blue hues instead of pure black
  static const Color primary = Color(0xFF38BDF8); // Tailwind Light Blue 400
  static const Color primaryDark = Color(0xFF0284C7);
  static const Color primaryLight = Color(0xFFBAE6FD);
  static const Color accent = Color(0xFF10B981); // Emerald 500

  static const Color background = Color(0xFF0F172A); // Slate 900
  static const Color surface = Color(0xFF1E293B); // Slate 800
  static const Color surfaceMuted = Color(0xFF334155); // Slate 700
  static const Color surfaceVariant = Color(0xFF334155);
  static const Color outlineLight = Color(0xFF475569); // Slate 600
  static const Color border = Color(0xFF334155);

  static const Color textPrimary = Color(0xFFF8FAFC); // Slate 50
  static const Color textSecondary = Color(0xFF94A3B8); // Slate 400
  static const Color textOnPrimary = Color(0xFF0F172A); // Slate 900
  static const Color textDisabled = Color(0xFF64748B); // Slate 500

  // --- operational failure ---
  static const Color danger = Color(0xFFEF4444);
  static const Color dangerSurface = Color(0xFF451A1A);

  // --- dose status ---
  // Vibrancy adjusted for contrast on #1E293B surface
  static const Color statusPending = Color(0xFF94A3B8);
  static const Color statusTaken = Color(0xFF22C55E);
  static const Color statusSkipped = Color(0xFFF59E0B);
  static const Color statusMissed = Color(0xFFEF4444);
  static const Color statusSnoozed = Color(0xFFA855F7);
  static const Color statusUnknown = Color(0xFF64748B);

  // --- risk level ---
  // The backend's SafetyAssessment.risk_level vocabulary, exactly.
  static const Color riskLow = Color(0xFF22C55E);
  static const Color riskModerate = Color(0xFFF59E0B);
  static const Color riskHigh = Color(0xFFF97316);
  static const Color riskCritical = Color(0xFFEF4444);

  // --- trust tiers ---
  // These three exist so the provenance separation the backend maintains cannot be
  // flattened by the UI. 
  //   deterministicFinding — a rules-engine output. Reproducible, auditable.
  //   verifiedEvidence     — retrieved from the clinical knowledge base, cited.
  //   aiAssisted           — generated. Nothing in this codebase produces this yet.
  static const Color deterministicFinding = Color(0xFFF87171); // Red 400
  static const Color deterministicFindingSurface = Color(0xFF451A1A); // Dark Red tinted
  static const Color verifiedEvidence = Color(0xFF38BDF8); // Light Blue 400
  static const Color verifiedEvidenceSurface = Color(0xFF16324A); // Dark Blue tinted
  static const Color aiAssisted = Color(0xFFC084FC); // Purple 400
  static const Color aiAssistedSurface = Color(0xFF3B205E); // Dark Purple tinted
}
