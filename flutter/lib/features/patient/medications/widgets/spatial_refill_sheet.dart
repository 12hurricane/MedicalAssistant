import 'dart:ui';

import 'package:flutter/material.dart';

import '../../../../app/theme/app_colors.dart';

/// Refill status — a shell, not a feature.
///
/// **Nothing calls this yet, and it must not be wired up as-is.** There is no refill
/// endpoint on the backend: no pharmacy record, no insurance eligibility, no dispense
/// ETA, no copay. `grep` for `showSpatialRefillSheet` returns this file only.
///
/// It arrived populated with the Stitch mockup's placeholder text as though those were
/// real values: "Today, 4 PM", "CVS Pharmacy", "Insurance Approved", "Covered by
/// BlueCross PPO", "\$15.00". In a mockup that is filler. Compiled into a shipping
/// widget it is the app telling a patient their medication is covered and will arrive
/// this afternoon, with nothing behind the claim — and cost and coverage are exactly the
/// facts someone decides whether to take a dose on. Two of the placeholders were also
/// the compile errors that broke the build (`BoxShadow(inset:)` and
/// `TextStyle(uppercase:)`, both CSS properties with no Flutter equivalent).
///
/// So the sheet now states what it is. When the refill endpoint exists, replace
/// [_UnavailableNotice] with real fields and delete this paragraph.
Future<void> showSpatialRefillSheet(
  BuildContext context, {
  required String medicationName,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    elevation: 0,
    builder: (context) => SpatialRefillSheet(medicationName: medicationName),
  );
}

class SpatialRefillSheet extends StatefulWidget {
  const SpatialRefillSheet({super.key, required this.medicationName});

  final String medicationName;

  @override
  State<SpatialRefillSheet> createState() => _SpatialRefillSheetState();
}

class _SpatialRefillSheetState extends State<SpatialRefillSheet>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _scaleAnimation = Tween<double>(begin: 0.9, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOutBack),
    );
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scaleAnimation,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 32),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(32),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.surface.withValues(alpha: 0.85),
                borderRadius: BorderRadius.circular(32),
                border: Border.all(
                  color: AppColors.surface.withValues(alpha: 0.8),
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.textPrimary.withValues(alpha: 0.2),
                    blurRadius: 40,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Center(
                    child: Container(
                      width: 48,
                      height: 6,
                      decoration: BoxDecoration(
                        color: AppColors.border,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Center(
                    child: Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: const RadialGradient(
                          colors: [AppColors.surfaceMuted, AppColors.border],
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: AppColors.textPrimary.withValues(alpha: 0.1),
                            blurRadius: 16,
                            offset: const Offset(0, 8),
                          ),
                          // An inner highlight was attempted here with
                          // `BoxShadow(inset: true)`. Flutter has no inset shadow; the
                          // radial gradient above does that job.
                        ],
                      ),
                      child: const Icon(
                        Icons.medication_liquid_rounded,
                        size: 64,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    // `TextStyle` has no `uppercase` flag — that is a CSS
                    // `text-transform`. Uppercase the string instead.
                    'REFILL STATUS'.toUpperCase(),
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textSecondary.withValues(alpha: 0.8),
                      letterSpacing: 1.5,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    widget.medicationName,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 24),
                  const _UnavailableNotice(),
                  const SizedBox(height: 24),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.textSecondary,
                    ),
                    child: const Text(
                      'Close',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Says there is no data, rather than showing plausible numbers.
///
/// Deliberately plain. Styling this as a filled status card would give absence the same
/// visual weight as a finding, which is the confusion the whole trust-tier palette in
/// [AppColors] exists to prevent.
class _UnavailableNotice extends StatelessWidget {
  const _UnavailableNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.info_outline_rounded,
            color: AppColors.textSecondary,
            size: 22,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Refill tracking is not available yet',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ).copyWith(fontSize: 14),
                ),
                const SizedBox(height: 4),
                const Text(
                  'This app has no connection to a pharmacy or insurer, so it cannot '
                  'tell you delivery timing, coverage or cost. Check with your '
                  'pharmacy for those.',
                  style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
