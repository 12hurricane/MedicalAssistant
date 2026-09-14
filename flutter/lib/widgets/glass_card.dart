import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';

/// Clinical surface card.
///
/// Replaces legacy glassmorphic backdrop filters and shadows with a flat,
/// high-contrast clinical card adhering strictly to audit-ready UI standards.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(24),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(4.0),
        border: Border.all(
          color: AppColors.border,
          width: 1.0,
        ),
      ),
      child: child,
    );
  }
}
