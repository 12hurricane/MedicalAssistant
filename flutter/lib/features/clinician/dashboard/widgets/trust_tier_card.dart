import 'package:flutter/material.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';

enum TrustTierType {
  deterministic,
  verifiedEvidence,
  aiAssisted,
}

/// A container that enforces the visual separation of the three clinical trust tiers.
///
/// See `AppColors` trust tiers documentation for the design rules this implements.
class TrustTierCard extends StatelessWidget {
  const TrustTierCard({
    super.key,
    required this.type,
    required this.title,
    this.content,
    this.icon,
    this.isEmpty = false,
    this.emptyMessage,
  });

  final TrustTierType type;
  final String title;
  final Widget? content;
  final IconData? icon;

  /// If true, renders the explicitly designed empty state rather than the content.
  final bool isEmpty;

  /// The message to display when [isEmpty] is true.
  final String? emptyMessage;

  Color get _borderColor => switch (type) {
        TrustTierType.deterministic => AppColors.deterministicFinding,
        TrustTierType.verifiedEvidence => AppColors.verifiedEvidence,
        TrustTierType.aiAssisted => AppColors.aiAssisted,
      };

  Color get _surfaceColor => switch (type) {
        TrustTierType.deterministic => AppColors.deterministicFindingSurface,
        TrustTierType.verifiedEvidence => AppColors.verifiedEvidenceSurface,
        TrustTierType.aiAssisted => AppColors.aiAssistedSurface,
      };

  IconData get _defaultIcon => switch (type) {
        TrustTierType.deterministic => Icons.warning_amber_rounded,
        TrustTierType.verifiedEvidence => Icons.description_outlined,
        TrustTierType.aiAssisted => Icons.auto_awesome,
      };

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: _surfaceColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _borderColor.withValues(alpha: 0.3), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(color: _borderColor.withValues(alpha: 0.15)),
              ),
            ),
            child: Row(
              children: [
                Icon(icon ?? _defaultIcon, size: 16, color: _borderColor),
                const SizedBox(width: 8),
                Text(
                  title.toUpperCase(),
                  style: AppTypography.tierBadge.copyWith(color: _borderColor),
                ),
              ],
            ),
          ),
          // Content
          Padding(
            padding: const EdgeInsets.all(16),
            child: isEmpty ? _buildEmptyState() : (content ?? const SizedBox()),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Row(
      children: [
        Icon(
          Icons.info_outline,
          color: _borderColor.withValues(alpha: 0.5),
          size: 20,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            emptyMessage ?? 'No data available for this tier.',
            style: AppTypography.bodyMedium.copyWith(
              color: _borderColor.withValues(alpha: 0.8),
              fontStyle: FontStyle.italic,
            ),
          ),
        ),
      ],
    );
  }
}

/// Specialized factory for the AI Fallback state.
class AiFallbackCard extends StatelessWidget {
  const AiFallbackCard({super.key});

  @override
  Widget build(BuildContext context) {
    return TrustTierCard(
      type: TrustTierType.aiAssisted,
      title: 'AI-Assisted Summary',
      isEmpty: true,
      emptyMessage: 'AI summary unavailable — deterministic findings apply.',
      icon: Icons.auto_awesome_outlined,
    );
  }
}

/// Specialized factory for the Deterministic Empty state.
class DeterministicEmptyCard extends StatelessWidget {
  const DeterministicEmptyCard({super.key});

  @override
  Widget build(BuildContext context) {
    return const TrustTierCard(
      type: TrustTierType.deterministic,
      title: 'Deterministic Safety Finding',
      isEmpty: true,
      emptyMessage: 'No deterministic findings flagged.',
      icon: Icons.check_circle_outline,
    );
  }
}
