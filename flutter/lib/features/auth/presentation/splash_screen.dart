import 'package:flutter/material.dart';

import '../../../app/theme/app_colors.dart';
import '../../../app/theme/app_typography.dart';

/// Shown while the stored session is being confirmed against the backend.
///
/// Its only job is to occupy the gap. The router leaves this route as soon as
/// [AuthController] resolves to signed-in or signed-out, so nothing here is tappable
/// and there is nothing to get stuck on.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.monitor_heart_outlined, size: 72, color: AppColors.primary),
            const SizedBox(height: 16),
            const Text('MedAssist AI', style: AppTypography.headlineMedium),
            const SizedBox(height: 8),
            const Text('Intelligent Medication Management', style: AppTypography.bodyMedium),
            const SizedBox(height: 48),
            const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(strokeWidth: 2.5, color: AppColors.primary),
            ),
            const SizedBox(height: 16),
            const Text('Restoring secure session...', style: AppTypography.bodyMedium),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.lock_outline, size: 16, color: AppColors.textSecondary),
                const SizedBox(width: 4),
                Text('Secure sign-in', style: AppTypography.labelSmall),
              ],
            )
          ],
        ),
      ),
    );
  }
}
