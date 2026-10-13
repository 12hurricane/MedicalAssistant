import 'package:flutter/material.dart';

import '../../../app/theme/app_colors.dart';

/// Premium Dark UI background for authentication screens.
///
/// Features a highly controlled, subtle radial gradient to provide depth
/// and a modern aesthetic, without sacrificing contrast or readability.
class AuthBackground extends StatelessWidget {
  const AuthBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: const BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(-0.8, -0.8), // Top left corner
          radius: 1.5,
          colors: [
            AppColors.surfaceMuted, // Subtle glow
            AppColors.background,   // Deep slate
          ],
          stops: [0.0, 1.0],
        ),
      ),
      child: SafeArea(child: child),
    );
  }
}
