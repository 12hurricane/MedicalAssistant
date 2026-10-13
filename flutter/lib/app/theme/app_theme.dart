import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'app_typography.dart';

/// The app's single [ThemeData].
///
/// Refactored for a Premium Dark UI approach.
/// Features Material 3, deep slate backgrounds, increased border radii (Cupertino-style),
/// and subtle elevation for a modern 3D feel without compromising clinical accessibility.
class AppTheme {
  const AppTheme._();

  /// 48dp minimum for anything tappable. "Yes, I took it" is pressed by people with
  /// tremor, and by people holding a phone in one hand at a bedside.
  static const double minTapTarget = 48;

  // Premium iOS-style border radius for cards and inputs
  static const double borderRadiusLarge = 16.0;
  static const double borderRadiusMedium = 12.0;

  static ThemeData get dark {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.dark,
    ).copyWith(
      primary: AppColors.primary,
      onPrimary: AppColors.textOnPrimary,
      secondary: AppColors.accent,
      surface: AppColors.surface,
      onSurface: AppColors.textPrimary,
      error: AppColors.statusMissed,
      outline: AppColors.border,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.background,
      textTheme: AppTypography.textTheme,
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 2, // Subtle 3D elevation on scroll
        centerTitle: false,
        titleTextStyle: AppTypography.titleLarge,
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 2, // Subtle 3D shadow 
        shadowColor: Colors.black.withValues(alpha: 0.4),
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(borderRadiusLarge),
          side: const BorderSide(color: AppColors.border, width: 0.5), // Minimalist border
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(minTapTarget),
          textStyle: AppTypography.labelLarge,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(borderRadiusMedium)),
          elevation: 1, // Subtle 3D pop for buttons
        ).copyWith(
          overlayColor: WidgetStateProperty.resolveWith((states) {
            if (states.contains(WidgetState.pressed)) {
              return AppColors.primaryDark.withValues(alpha: 0.2);
            }
            if (states.contains(WidgetState.hovered)) {
              return AppColors.primaryLight.withValues(alpha: 0.1);
            }
            return null;
          }),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(minTapTarget),
          textStyle: AppTypography.labelLarge,
          foregroundColor: AppColors.primary,
          side: const BorderSide(color: AppColors.primary),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(borderRadiusMedium)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          minimumSize: const Size(minTapTarget, minTapTarget),
          textStyle: AppTypography.labelLarge,
          foregroundColor: AppColors.primary,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: WidgetStateColor.resolveWith((states) {
          if (states.contains(WidgetState.focused)) {
            return AppColors.primaryDark.withValues(alpha: 0.1);
          }
          if (states.contains(WidgetState.error)) {
            return AppColors.dangerSurface;
          }
          return AppColors.surface;
        }),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(borderRadiusMedium),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(borderRadiusMedium),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(borderRadiusMedium),
          borderSide: const BorderSide(color: AppColors.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(borderRadiusMedium),
          borderSide: const BorderSide(color: AppColors.statusMissed),
        ),
        labelStyle: AppTypography.bodyMedium.copyWith(color: AppColors.textSecondary),
        hintStyle: AppTypography.bodyMedium.copyWith(color: AppColors.textDisabled),
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.border,
        thickness: 1,
        space: 1,
      ),
      radioTheme: RadioThemeData(
        fillColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? AppColors.primary
              : AppColors.textSecondary,
        ),
      ),
      snackBarTheme: const SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.surfaceVariant, // Using slate variant
        contentTextStyle: TextStyle(color: AppColors.textPrimary, fontSize: 15),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.primary,
        linearTrackColor: AppColors.surfaceMuted,
      ),
    );
  }
}
