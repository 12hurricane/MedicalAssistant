import 'package:flutter/material.dart';
import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/generated/api_models.dart';

class AllClearView extends StatelessWidget {
  const AllClearView({super.key, required this.analysis});

  final AdherenceAnalysisResult analysis;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildEmeraldBanner(),
        const SizedBox(height: 16),
        _buildGenerativeSummary(),
        const SizedBox(height: 16),
        _buildPatientGuidanceCard(),
      ],
    );
  }

  Widget _buildEmeraldBanner() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0x4D022C22), // emerald-950/30
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xB310B981), width: 1.5), // emerald-500/70
        boxShadow: const [
          BoxShadow(
            color: Color(0x2610B981), // emerald-500/15
            blurRadius: 20,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xCC022C22), // emerald-950/80
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: const Color(0x8010B981)), // emerald-500/50
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.verified, color: Color(0xFF6EE7B7), size: 14), // emerald-300
                      SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          '[TIER 1] DETERMINISTIC SAFETY FINDING',
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 0.5,
                            color: Color(0xFF6EE7B7),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                'STATUS: ${analysis.safetyRiskLevel.toUpperCase()}',
                style: const TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF34D399), // emerald-400
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: const Color(0x3310B981), // emerald-500/20
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0x6610B981)), // emerald-500/40
                ),
                child: const Icon(Icons.task_alt, color: Color(0xFF34D399), size: 24),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'All Clear: No Safety Concerns Detected',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -0.5,
                        color: Color(0xFFA7F3D0), // emerald-200
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (analysis.recommendedAction.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surface.withValues(alpha: 0.8),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: const Color(0x3310B981)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.info_outline, size: 16, color: Color(0xFF34D399)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'RECOMMENDED ACTION',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 0.5,
                            color: Color(0xFF34D399),
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          analysis.recommendedAction,
                          style: const TextStyle(fontSize: 13, color: AppColors.textPrimary),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildGenerativeSummary() {
    final insights = analysis.clinicalBrief.insights;
    final hasInsights = insights != null;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'ADHERENCE SUMMARY',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.5,
                  color: AppColors.textSecondary,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: hasInsights
                      ? const Color(0x2610B981)
                      : AppColors.surfaceVariant,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(
                    color: hasInsights
                        ? const Color(0xFF10B981)
                        : AppColors.border,
                  ),
                ),
                child: Text(
                  hasInsights ? 'AI-ENRICHED' : 'DETERMINISTIC',
                  style: TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                    color: hasInsights
                        ? const Color(0xFF10B981)
                        : AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            analysis.patientExplanation.summary,
            style: AppTypography.narrative,
          ),
          if (hasInsights && insights.trend != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'Trend: ${insights.trend}',
                style: const TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 11,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(Icons.info_outline, size: 12, color: AppColors.textDisabled),
              const SizedBox(width: 4),
              Text(
                hasInsights
                    ? 'AI-enriched — Always verify with clinician.'
                    : 'Deterministic analysis — no LLM involved.',
                style: const TextStyle(fontSize: 10, color: AppColors.textDisabled),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPatientGuidanceCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'SYSTEM FINDINGS & GUIDANCE',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            analysis.patientExplanation.whatTheSystemFound,
            style: const TextStyle(
              fontSize: 14,
              height: 1.5,
              color: AppColors.textPrimary,
            ),
          ),
          if (analysis.patientExplanation.whatToDoNext.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(8),
                border: const Border(left: BorderSide(color: AppColors.primary, width: 2)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'NEXT STEPS',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 0.5,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    analysis.patientExplanation.whatToDoNext,
                    style: const TextStyle(
                      fontSize: 13,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
