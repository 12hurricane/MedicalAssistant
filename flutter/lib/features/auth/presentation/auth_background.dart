import 'package:flutter/material.dart';

import '../../../app/theme/app_colors.dart';

/// Flat, high-contrast background for clinical authentication screens.
///
/// Strictly eliminates consumer SaaS decorative gradients, blurred ambient blobs,
/// and backdrop filters to preserve visual clarity, accessibility, and audit readiness.
class AuthBackground extends StatelessWidget {
  const AuthBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: const BoxDecoration(
        color: AppColors.background,
      ),
      child: SafeArea(child: child),
    );
  }
}
