import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Type scale.
///
/// Two decisions worth keeping when the visual design is replaced:
///
/// - **No hard-coded font family.** The platform default carries the user's accessibility
///   font settings; a bundled font would silently drop them. Medication names and
///   dose strengths are exactly the text a patient with poor eyesight needs to enlarge.
/// - **[doseStrength] is a distinct token.** "500 mg" is not body copy — a misread
///   strength is a clinical error, so it gets its own weight and letter spacing and is
///   never rendered in the same style as the surrounding sentence.
class AppTypography {
  const AppTypography._();

  static const TextStyle displayLarge = TextStyle(
    fontSize: 32,
    height: 1.2,
    fontWeight: FontWeight.w900,
    color: AppColors.textPrimary,
  );

  static const TextStyle headlineMedium = TextStyle(
    fontSize: 24,
    height: 1.25,
    fontWeight: FontWeight.w800,
    color: AppColors.textPrimary,
  );

  static const TextStyle titleLarge = TextStyle(
    fontSize: 20,
    height: 1.3,
    fontWeight: FontWeight.w600,
    color: AppColors.textPrimary,
  );

  static const TextStyle titleMedium = TextStyle(
    fontSize: 17,
    height: 1.35,
    fontWeight: FontWeight.w600,
    color: AppColors.textPrimary,
  );

  static const TextStyle bodyLarge = TextStyle(
    fontSize: 16,
    height: 1.45,
    fontWeight: FontWeight.w500,
    color: AppColors.textPrimary,
  );

  static const TextStyle bodyMedium = TextStyle(
    fontSize: 14,
    height: 1.45,
    fontWeight: FontWeight.w300,
    color: AppColors.textSecondary,
  );

  static const TextStyle labelLarge = TextStyle(
    fontSize: 15,
    height: 1.2,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.1,
  );

  static const TextStyle labelSmall = TextStyle(
    fontSize: 12,
    height: 1.2,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.4,
    color: AppColors.textSecondary,
  );

  /// For "500 mg", "1 tablet". Tabular figures so a column of strengths lines up.
  static const TextStyle doseStrength = TextStyle(
    fontSize: 16,
    height: 1.3,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.2,
    color: AppColors.textPrimary,
    fontFeatures: [FontFeature.tabularFigures()],
  );

  /// For "1:00 PM". Also tabular, for the same reason.
  static const TextStyle doseTime = TextStyle(
    fontSize: 15,
    height: 1.3,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.2,
    color: AppColors.textSecondary,
    fontFeatures: [FontFeature.tabularFigures()],
  );

  /// The all-caps banner on a trust-tier section header.
  static const TextStyle tierBadge = TextStyle(
    fontSize: 11,
    height: 1.1,
    fontWeight: FontWeight.w800,
    letterSpacing: 0.9,
  );

  /// The serif style for AI-generated narrative ("a system wrote you a sentence" tier).
  static const TextStyle narrative = TextStyle(
    fontSize: 15,
    height: 1.5,
    fontFamily: 'serif',
    fontWeight: FontWeight.w400,
    color: AppColors.textPrimary,
  );

  static TextTheme get textTheme => const TextTheme(
        displayLarge: displayLarge,
        headlineMedium: headlineMedium,
        titleLarge: titleLarge,
        titleMedium: titleMedium,
        bodyLarge: bodyLarge,
        bodyMedium: bodyMedium,
        labelLarge: labelLarge,
        labelSmall: labelSmall,
      );
}
