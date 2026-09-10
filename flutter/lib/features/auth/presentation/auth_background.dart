import 'package:flutter/material.dart';

import '../../../app/theme/app_colors.dart';

/// A premium, animated-feeling background for the auth screens.
/// Features a soft gradient with abstract ambient shapes.
class AuthBackground extends StatelessWidget {
  const AuthBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.primaryLight,
            Color(0xFFF0F7FA), // Soft cyan-ish white
            Color(0xFFE8E5F4), // Soft purple tint
          ],
          stops: [0.0, 0.5, 1.0],
        ),
      ),
      child: Stack(
        children: [
          // Ambient blurred blob 1
          Positioned(
            top: -100,
            left: -100,
            child: Container(
              width: 400,
              height: 400,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.primary.withValues(alpha: 0.15),
              ),
            ),
          ),
          // Ambient blurred blob 2
          Positioned(
            bottom: -50,
            right: -100,
            child: Container(
              width: 500,
              height: 500,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.accent.withValues(alpha: 0.1),
              ),
            ),
          ),
          // Ambient blurred blob 3
          Positioned(
            top: 200,
            right: -150,
            child: Container(
              width: 300,
              height: 300,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.aiAssisted.withValues(alpha: 0.1),
              ),
            ),
          ),
          // Content
          SafeArea(child: child),
        ],
      ),
    );
  }
}
