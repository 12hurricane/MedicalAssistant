import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';

/// Adherence, drawn as a glass torus.
///
/// [rate] is nullable and that is the point of this widget's contract. The backend
/// returns `adherence_rate: null` when `expected_doses` is zero, and the generated model
/// carries the rule verbatim: *a null rate means "not measurable", NOT zero and NOT
/// 100%*. That agreement exists because an earlier version computed
/// `taken / max(expected, 1)` and a patient with no schedule at all was congratulated
/// with a perfect score.
///
/// The first spatial version of this widget took a non-nullable `double percentage`,
/// which quietly moved the decision to the call site — where the only options are
/// `?? 0` (renders 0%, reads as total non-adherence) and `?? 1` (renders 100%, reads as
/// perfect). Both are assertions about a patient the app has no data for. Keeping the
/// null here means the no-data branch is the compiler's business, not a caller's
/// judgement call.
class SpatialAdherenceTorus extends StatefulWidget {
  const SpatialAdherenceTorus({
    super.key,
    required this.rate,
    this.size = 120.0,
    this.strokeWidth = 24.0,
  });

  /// Adherence as a fraction in 0..1, or null when there were no expected doses.
  final double? rate;

  final double size;
  final double strokeWidth;

  @override
  State<SpatialAdherenceTorus> createState() => _SpatialAdherenceTorusState();
}

class _SpatialAdherenceTorusState extends State<SpatialAdherenceTorus>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  /// What the arc sweeps to. Null rate parks it at zero, but nothing is drawn in that
  /// case anyway — see [build], which never reaches the painter's fill branch.
  double get _target => (widget.rate ?? 0).clamp(0.0, 1.0);

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    _animation = Tween<double>(begin: 0.0, end: _target).animate(
      // `easeOutBack` overshoots, which is fine for a bar and wrong for a percentage —
      // it would briefly render a number above the real one. `easeOutCubic` settles
      // from below.
      CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic),
    );
    _controller.forward();
  }

  @override
  void didUpdateWidget(SpatialAdherenceTorus oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.rate != widget.rate) {
      _animation = Tween<double>(begin: _animation.value, end: _target).animate(
        CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic),
      );
      _controller.forward(from: 0.0);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final rate = widget.rate;

    // No-data: an empty track, an em dash, and the words. Not a 0% ring, which is a
    // measurement, and not a full one, which is a compliment.
    if (rate == null) {
      return SizedBox(
        width: widget.size,
        height: widget.size,
        child: CustomPaint(
          painter: _TorusPainter(sweep: 0, strokeWidth: widget.strokeWidth),
          child: const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '—',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    color: AppColors.textDisabled,
                  ),
                ),
                Text(
                  'No doses yet',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textDisabled,
                    letterSpacing: 0.3,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _animation,
        builder: (context, child) {
          return CustomPaint(
            painter: _TorusPainter(
              sweep: _animation.value,
              strokeWidth: widget.strokeWidth,
            ),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    // Rounded, not truncated: `.toInt()` turned 79.6% into "79".
                    '${(_animation.value * 100).round()}%',
                    style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                      color: AppColors.primaryDark,
                      letterSpacing: -1,
                    ),
                  ),
                  const Text(
                    'Adherence',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textSecondary,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _TorusPainter extends CustomPainter {
  const _TorusPainter({required this.sweep, required this.strokeWidth});

  /// 0..1. Zero draws the track only.
  final double sweep;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;

    final shadowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4.0)
      ..color = AppColors.textPrimary.withValues(alpha: 0.05);

    final trackPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..color = AppColors.surfaceMuted.withValues(alpha: 0.9);

    canvas.drawCircle(center, radius, shadowPaint);
    canvas.drawCircle(center, radius, trackPaint);

    if (sweep <= 0) return;

    final sweepAngle = 2 * math.pi * sweep;
    final rect = Rect.fromCircle(center: center, radius: radius);

    final gradient = SweepGradient(
      startAngle: -math.pi / 2,
      endAngle: -math.pi / 2 + sweepAngle,
      colors: const [
        AppColors.statusTaken,
        AppColors.accent,
        AppColors.statusTaken,
      ],
      stops: const [0.0, 0.5, 1.0],
    );

    canvas.drawArc(
      rect,
      -math.pi / 2,
      sweepAngle,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth
        ..strokeCap = StrokeCap.round
        ..shader = gradient.createShader(rect),
    );

    // Specular highlight, inset, to round the tube off.
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius - (strokeWidth * 0.25)),
      -math.pi / 2,
      sweepAngle,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth * 0.2
        ..strokeCap = StrokeCap.round
        ..color = Colors.white.withValues(alpha: 0.3)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.0),
    );
  }

  @override
  bool shouldRepaint(covariant _TorusPainter oldDelegate) =>
      oldDelegate.sweep != sweep || oldDelegate.strokeWidth != strokeWidth;
}
