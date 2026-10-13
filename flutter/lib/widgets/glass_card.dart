import 'package:flutter/material.dart';

/// Premium clinical surface card.
///
/// Uses subtle elevation (3D feel) and increased border radius (Cupertino-style)
/// while maintaining strict clinical safety contrast and omitting heavy blur effects.
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
    return Card(
      // The theme provides the elevation, color, and border radius.
      child: Padding(
        padding: padding,
        child: child,
      ),
    );
  }
}
