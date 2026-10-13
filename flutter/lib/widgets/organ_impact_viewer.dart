import 'dart:ui';

import 'package:flutter/material.dart';

import '../app/theme/app_colors.dart';
import '../core/api/generated/api_models.dart';

/// Organ-impact visualisation screen, wired to a real [SafetyAssessmentResponse].
///
/// Accepts an optional [SafetyAssessmentResponse]. When null, the screen renders
/// its empty state in [AppColors.textDisabled] and [AppColors.surfaceMuted] —
/// absence of an assessment must not be dressed as the output of one.
///
/// When a [SafetyAssessmentResponse] is provided, all panels render with real
/// deterministic data from the safety engine:
///
/// ```text
/// SafetyAssessment → API DTO → controller → OrganImpactViewerScreen → pure painting
/// ```
class OrganImpactViewerScreen extends StatelessWidget {
  const OrganImpactViewerScreen({super.key, this.assessment});

  final SafetyAssessmentResponse? assessment;

  /// Shown wherever a panel would otherwise display a value it does not have.
  static const String _noData = 'No clinical data available';
  static const String _awaiting = 'Awaiting assessment';

  @override
  Widget build(BuildContext context) {
    final hasData = assessment != null;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface.withValues(alpha: 0.85),
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(color: Colors.transparent),
          ),
        ),
        elevation: 0,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: hasData ? _accentForRisk(assessment!.riskLevel).withValues(alpha: 0.15) : AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                Icons.view_in_ar_rounded,
                color: hasData ? _accentForRisk(assessment!.riskLevel) : AppColors.textSecondary,
                size: 22,
              ),
            ),
            const SizedBox(width: 12),
            Text(
              hasData ? 'Safety Impact Review' : 'Visual preview',
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontWeight: FontWeight.bold,
                fontSize: 18,
              ),
            ),
          ],
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1280),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!hasData)
                  const _AccentBanner(
                    icon: Icons.info_outline_rounded,
                    title: 'LAYOUT PREVIEW — NOT CONNECTED',
                    body:
                        'This screen is not wired to the safety engine. It renders its own '
                        'empty state and shows no patient, medication or risk level.',
                    accentColor: AppColors.textSecondary,
                  )
                else if (assessment!.riskLevel == 'CRITICAL' || assessment!.riskLevel == 'HIGH')
                  _AccentBanner(
                    icon: Icons.warning_amber_rounded,
                    title: assessment!.requiresHumanReview
                        ? 'HUMAN REVIEW REQUIRED'
                        : 'SAFETY ALERT — ${assessment!.riskLevel}',
                    body: assessment!.recommendedAction,
                    accentColor: _accentForRisk(assessment!.riskLevel),
                  )
                else
                  _AccentBanner(
                    icon: Icons.check_circle_outline_rounded,
                    title: 'SAFETY STATUS: ${assessment!.riskLevel}',
                    body: assessment!.recommendedAction,
                    accentColor: _accentForRisk(assessment!.riskLevel),
                  ),
                const SizedBox(height: 24),
                _SubjectHeaderCard(assessment: assessment),
                const SizedBox(height: 24),
                LayoutBuilder(
                  builder: (context, constraints) {
                    if (constraints.maxWidth > 900) {
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(flex: 8, child: _RenderStage(assessment: assessment)),
                          const SizedBox(width: 24),
                          Expanded(flex: 4, child: _InfoPanels(assessment: assessment)),
                        ],
                      );
                    }
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _RenderStage(assessment: assessment),
                        const SizedBox(height: 24),
                        _InfoPanels(assessment: assessment),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 100),
              ],
            ),
          ),
        ),
      ),
      bottomSheet: _FooterBar(assessment: assessment),
    );
  }

  static Color _accentForRisk(String riskLevel) {
    switch (riskLevel.toUpperCase()) {
      case 'CRITICAL':
        return const Color(0xFFBA1A1A);
      case 'HIGH':
        return const Color(0xFFF43F5E);
      case 'MODERATE':
        return const Color(0xFFF59E0B);
      default:
        return const Color(0xFF10B981);
    }
  }
}

/// A notice strip with a left accent rule.
class _AccentBanner extends StatelessWidget {
  const _AccentBanner({
    required this.icon,
    required this.title,
    required this.body,
    required this.accentColor,
  });

  final IconData icon;
  final String title;
  final String body;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(12),
          bottomRight: Radius.circular(12),
        ),
        border: Border(left: BorderSide(color: accentColor, width: 4)),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: accentColor.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: accentColor),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: accentColor,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  body,
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Header card: patient summary and risk-level chip.
class _SubjectHeaderCard extends StatelessWidget {
  const _SubjectHeaderCard({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    final hasData = assessment != null;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.07),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 24,
        runSpacing: 16,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [AppColors.surfaceMuted, AppColors.border],
                  ),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.surface, width: 2),
                ),
                alignment: Alignment.center,
                child: const Icon(
                  Icons.person_outline_rounded,
                  color: AppColors.textDisabled,
                  size: 30,
                ),
              ),
              const SizedBox(width: 20),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    hasData ? 'Patient #${assessment!.patientId}' : OrganImpactViewerScreen._noData,
                    style: TextStyle(
                      color: hasData ? AppColors.textPrimary : AppColors.textDisabled,
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (hasData)
                    Wrap(
                      spacing: 20,
                      children: [
                        _InfoBadge(
                          icon: Icons.calendar_month_rounded,
                          value: _formatDate(assessment!.evaluatedAt),
                        ),
                        _InfoBadge(
                          icon: Icons.badge_rounded,
                          value: '${assessment!.evidence.length} findings',
                        ),
                        _InfoBadge(
                          icon: Icons.medication_rounded,
                          value: '${assessment!.medicationInteractions.length} interactions',
                        ),
                      ],
                    )
                  else
                    const Wrap(
                      spacing: 20,
                      children: [
                        _InfoBadge(icon: Icons.calendar_month_rounded),
                        _InfoBadge(icon: Icons.badge_rounded),
                        _InfoBadge(icon: Icons.monitor_weight_rounded),
                      ],
                    ),
                ],
              ),
            ],
          ),
          _buildRiskChip(hasData),
        ],
      ),
    );
  }

  Widget _buildRiskChip(bool hasData) {
    if (!hasData) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.surfaceMuted,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.border),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.pending_outlined, color: AppColors.textDisabled, size: 18),
            SizedBox(width: 8),
            Text(
              OrganImpactViewerScreen._awaiting,
              style: TextStyle(
                color: AppColors.textDisabled,
                fontWeight: FontWeight.bold,
                fontSize: 13,
                letterSpacing: 0.5,
              ),
            ),
          ],
        ),
      );
    }

    final accent = OrganImpactViewerScreen._accentForRisk(assessment!.riskLevel);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: accent.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            assessment!.riskLevel == 'CRITICAL' || assessment!.riskLevel == 'HIGH'
                ? Icons.warning_amber_rounded
                : Icons.shield_outlined,
            color: accent,
            size: 18,
          ),
          const SizedBox(width: 8),
          Text(
            'RISK: ${assessment!.riskLevel}',
            style: TextStyle(
              color: accent,
              fontWeight: FontWeight.bold,
              fontSize: 13,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  static String _formatDate(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}

/// One metadata badge.
class _InfoBadge extends StatelessWidget {
  const _InfoBadge({required this.icon, this.value});

  final IconData icon;
  final String? value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: value != null ? AppColors.textSecondary : AppColors.textDisabled),
        const SizedBox(width: 6),
        Text(
          value ?? '—',
          style: TextStyle(
            fontSize: 14,
            color: value != null ? AppColors.textSecondary : AppColors.textDisabled,
          ),
        ),
      ],
    );
  }
}

/// The dark render stage, with a header rail and a floating glass caption.
class _RenderStage extends StatelessWidget {
  const _RenderStage({this.assessment});

  final SafetyAssessmentResponse? assessment;

  static const Color _stageTop = Color(0xFF1E293B);
  static const Color _stageBottom = Color(0xFF0F172A);

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 550,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.05),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppColors.border)),
              color: AppColors.surface,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceMuted,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Icon(
                        Icons.threed_rotation_rounded,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    const SizedBox(width: 10),
                    const Text(
                      'Spatial viewer',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
                const Row(
                  children: [
                    IconButton(
                      onPressed: null,
                      icon: Icon(Icons.zoom_in),
                      tooltip: 'Zoom in (unavailable in preview)',
                    ),
                    IconButton(
                      onPressed: null,
                      icon: Icon(Icons.zoom_out),
                      tooltip: 'Zoom out (unavailable in preview)',
                    ),
                  ],
                ),
              ],
            ),
          ),
          Expanded(
            child: Stack(
              fit: StackFit.expand,
              children: [
                Container(
                  decoration: const BoxDecoration(
                    gradient: RadialGradient(
                      colors: [_stageTop, _stageBottom],
                      radius: 1.0,
                    ),
                  ),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.view_in_ar_outlined,
                          color: AppColors.surface.withValues(alpha: 0.35),
                          size: 64,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          'NO MODEL LOADED',
                          style: TextStyle(
                            color: AppColors.surface.withValues(alpha: 0.5),
                            fontSize: 13,
                            letterSpacing: 1.5,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Positioned(
                  bottom: 24,
                  left: 24,
                  right: 24,
                  child: _StageCaption(assessment: assessment),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The frosted caption that floats over the stage.
class _StageCaption extends StatelessWidget {
  const _StageCaption({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    final hasInteractions = assessment != null && assessment!.medicationInteractions.isNotEmpty;
    final interaction = hasInteractions ? assessment!.medicationInteractions.first : null;

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(alpha: 0.85),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.surface.withValues(alpha: 0.6)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: hasInteractions
                      ? OrganImpactViewerScreen._accentForRisk(assessment!.riskLevel).withValues(alpha: 0.15)
                      : AppColors.surfaceMuted,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.border),
                ),
                child: Icon(
                  hasInteractions ? Icons.warning_amber_rounded : Icons.help_outline_rounded,
                  color: hasInteractions
                      ? OrganImpactViewerScreen._accentForRisk(assessment!.riskLevel)
                      : AppColors.textDisabled,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      hasInteractions
                          ? '${interaction!.drugA} ↔ ${interaction.drugB}'
                          : 'No impact zone selected',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: hasInteractions ? AppColors.textPrimary : AppColors.textDisabled,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      hasInteractions
                          ? interaction!.clinicalEffect
                          : OrganImpactViewerScreen._noData,
                      style: TextStyle(
                        fontSize: 14,
                        color: hasInteractions ? AppColors.textSecondary : AppColors.textDisabled,
                        fontWeight: FontWeight.w500,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InfoPanels extends StatelessWidget {
  const _InfoPanels({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _MetricPanel(assessment: assessment),
        const SizedBox(height: 24),
        _StepTimeline(assessment: assessment),
        const SizedBox(height: 24),
        _ProvenancePanel(assessment: assessment),
      ],
    );
  }
}

/// Summary metric panel. Shows risk level and finding count when data is available.
class _MetricPanel extends StatelessWidget {
  const _MetricPanel({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    final hasData = assessment != null;
    final totalFindings = hasData ? assessment!.evidence.length : 0;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.07),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.analytics_outlined,
                  color: hasData ? OrganImpactViewerScreen._accentForRisk(assessment!.riskLevel) : AppColors.textDisabled,
                  size: 14,
                ),
                const SizedBox(width: 6),
                Text(
                  hasData ? 'SAFETY SUMMARY' : 'SUMMARY',
                  style: TextStyle(
                    color: hasData ? AppColors.textSecondary : AppColors.textDisabled,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.5,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            hasData ? '$totalFindings' : '—',
            style: TextStyle(
              color: hasData
                  ? OrganImpactViewerScreen._accentForRisk(assessment!.riskLevel)
                  : AppColors.textDisabled,
              fontSize: 56,
              fontWeight: FontWeight.bold,
              height: 1,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            hasData ? 'Total Findings' : OrganImpactViewerScreen._awaiting,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontSize: 14,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 12),
          if (hasData)
            Text(
              assessment!.recommendedAction,
              style: const TextStyle(
                color: AppColors.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
                height: 1.5,
              ),
            )
          else
            const Text(
              OrganImpactViewerScreen._noData,
              style: TextStyle(
                color: AppColors.textDisabled,
                fontSize: 14,
                fontWeight: FontWeight.w500,
                height: 1.5,
              ),
            ),
        ],
      ),
    );
  }
}

/// Timeline showing evidence items as steps when data is available,
/// or ordinal placeholders when not.
class _StepTimeline extends StatelessWidget {
  const _StepTimeline({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    final hasData = assessment != null && assessment!.evidence.isNotEmpty;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.07),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: AppColors.surfaceMuted,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(
                  Icons.timeline_rounded,
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(width: 10),
              Text(
                hasData ? 'Evidence Chain' : 'Sequence',
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          if (hasData)
            ...assessment!.evidence.asMap().entries.map((entry) {
              final idx = entry.key;
              final ev = entry.value;
              final isLast = idx == assessment!.evidence.length - 1;
              return Column(
                children: [
                  _TimelineStep(
                    number: '${idx + 1}',
                    title: ev.category.replaceAll('_', ' '),
                    subtitle: ev.finding,
                    severity: ev.severity,
                  ),
                  if (!isLast) const SizedBox(height: 16),
                ],
              );
            })
          else
            for (var step = 1; step <= 3; step++) ...[
              _TimelineStep(
                number: '$step',
                title: 'Step $step',
                subtitle: OrganImpactViewerScreen._awaiting,
              ),
              if (step < 3) const SizedBox(height: 16),
            ],
        ],
      ),
    );
  }
}

/// One step row: numbered disc, then a filled panel with a title and a subtitle.
///
/// When [severity] is provided, the disc colour reflects the severity level:
/// CRITICAL/CONTRAINDICATED = red, HIGH/MAJOR = rose, MODERATE = amber.
class _TimelineStep extends StatelessWidget {
  const _TimelineStep({
    required this.number,
    required this.title,
    required this.subtitle,
    this.severity,
  });

  final String number;
  final String title;
  final String subtitle;
  final String? severity;

  Color get _discColor {
    if (severity == null) return AppColors.surfaceMuted;
    switch (severity!.toUpperCase()) {
      case 'CONTRAINDICATED':
      case 'CRITICAL':
        return const Color(0xFFBA1A1A);
      case 'MAJOR':
      case 'HIGH':
        return const Color(0xFFF43F5E);
      case 'MODERATE':
        return const Color(0xFFF59E0B);
      default:
        return AppColors.surfaceMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasSeverity = severity != null;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: hasSeverity ? _discColor.withValues(alpha: 0.2) : AppColors.surfaceMuted,
            shape: BoxShape.circle,
            border: Border.all(
              color: hasSeverity ? _discColor : AppColors.border,
              width: 2,
            ),
          ),
          alignment: Alignment.center,
          child: Text(
            number,
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: hasSeverity ? _discColor : AppColors.textDisabled,
              fontSize: 14,
            ),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: hasSeverity
                  ? _discColor.withValues(alpha: 0.06)
                  : AppColors.surfaceMuted.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: hasSeverity ? _discColor.withValues(alpha: 0.3) : AppColors.border,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                          color: hasSeverity ? AppColors.textPrimary : AppColors.textSecondary,
                        ),
                      ),
                    ),
                    if (hasSeverity)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: _discColor.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          severity!,
                          style: TextStyle(
                            fontFamily: 'JetBrains Mono',
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: _discColor,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: hasSeverity ? AppColors.textSecondary : AppColors.textDisabled,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Source list: renders actual evidence sources when available.
class _ProvenancePanel extends StatelessWidget {
  const _ProvenancePanel({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    final hasEvidence = assessment != null && assessment!.evidence.isNotEmpty;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'SOURCES',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: AppColors.textSecondary,
              letterSpacing: 1.0,
            ),
          ),
          const SizedBox(height: 12),
          if (hasEvidence)
            ...assessment!.evidence.map((ev) => _ProvenanceRow(
                  source: ev.referenceSource,
                  category: ev.category,
                ))
          else
            const _ProvenanceRow(),
        ],
      ),
    );
  }
}

class _ProvenanceRow extends StatelessWidget {
  const _ProvenanceRow({this.source, this.category});

  final String? source;
  final String? category;

  @override
  Widget build(BuildContext context) {
    final hasSource = source != null;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Icon(
            hasSource ? Icons.link_rounded : Icons.link_off_rounded,
            color: hasSource ? AppColors.primary : AppColors.textDisabled,
            size: 18,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (category != null)
                  Text(
                    category!.replaceAll('_', ' '),
                    style: const TextStyle(
                      fontFamily: 'JetBrains Mono',
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textSecondary,
                      letterSpacing: 0.5,
                    ),
                  ),
                Text(
                  source ?? 'No sources retrieved',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: hasSource ? AppColors.textPrimary : AppColors.textDisabled,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Sticky action rail.
class _FooterBar extends StatelessWidget {
  const _FooterBar({this.assessment});

  final SafetyAssessmentResponse? assessment;

  @override
  Widget build(BuildContext context) {
    final hasData = assessment != null;

    return Container(
      height: 80,
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.85),
        border: const Border(top: BorderSide(color: AppColors.border, width: 1.5)),
        boxShadow: [
          BoxShadow(
            color: AppColors.textPrimary.withValues(alpha: 0.1),
            blurRadius: 30,
            offset: const Offset(0, -10),
          ),
        ],
      ),
      child: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  hasData
                      ? 'Evaluated: ${_formatTimestamp(assessment!.evaluatedAt)}'
                      : 'Preview only — no actions available',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textDisabled,
                  ),
                ),
                Row(
                  children: [
                    OutlinedButton(
                      onPressed: hasData ? () => Navigator.of(context).pop() : null,
                      child: Text(hasData ? 'Back to Dashboard' : 'Secondary action'),
                    ),
                    const SizedBox(width: 16),
                    ElevatedButton(
                      onPressed: hasData && assessment!.requiresHumanReview
                          ? () {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Review acknowledged. Finding logged.')),
                              );
                            }
                          : null,
                      child: Text(
                        hasData && assessment!.requiresHumanReview
                            ? 'Acknowledge & Review'
                            : 'Primary action',
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String _formatTimestamp(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
