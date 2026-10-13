import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/widgets/state_views.dart';
import '../dashboard/widgets/patient_background.dart';
import 'state/adherence_controller.dart';

/// Comprehensive adherence analytics and behavioral intelligence screen.
class AdherenceAnalyticsScreen extends ConsumerWidget {
  const AdherenceAnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metricsAsync = ref.watch(adherenceMetricsProvider);
    final period = ref.watch(adherencePeriodProvider);

    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        title: const Text(
          'Adherence Analytics',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
        ),
        backgroundColor: AppColors.surface,
        elevation: 0,
        shape: const Border(bottom: BorderSide(color: AppColors.border, width: 1)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: AppColors.textSecondary),
            tooltip: 'Refresh metrics',
            onPressed: () => ref.read(adherenceMetricsProvider.notifier).refresh(),
          ),
        ],
      ),
      body: PatientBackground(
        child: RefreshIndicator(
          onRefresh: () => ref.read(adherenceMetricsProvider.notifier).refresh(),
          child: switch (metricsAsync) {
            AsyncValue(hasValue: true, :final value?) => _buildContent(context, ref, value, period),
            AsyncValue(hasError: true, :final error?) => ErrorView(
                error: error,
                onRetry: () => ref.read(adherenceMetricsProvider.notifier).refresh(),
              ),
            _ => const LoadingView(label: 'Calculating adherence intelligence...'),
          },
        ),
      ),
    );
  }

  Widget _buildContent(
    BuildContext context,
    WidgetRef ref,
    AdherenceMetricsResponse metrics,
    String currentPeriod,
  ) {
    final rate = metrics.adherenceRate;
    final rateString = rate != null ? '${rate.toStringAsFixed(1)}%' : 'N/A';

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
      children: [
        // Period Selector
        _buildPeriodSelector(ref, currentPeriod),
        const SizedBox(height: 16),

        // Escalation Alert Banner if needed
        if (metrics.shouldEscalate) ...[
          _buildEscalationBanner(metrics),
          const SizedBox(height: 16),
        ],

        // Primary Score & Streaks Card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  // Circular / Gauge representation
                  Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      color: AppColors.surfaceVariant,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: _rateColor(rate),
                        width: 4,
                      ),
                    ),
                    child: Center(
                      child: Text(
                        rateString,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.bold,
                          color: _rateColor(rate),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Adherence Rate',
                          style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          rateString,
                          style: const TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            Icon(
                              metrics.trend == 'improving'
                                  ? Icons.trending_up
                                  : metrics.trend == 'declining'
                                      ? Icons.trending_down
                                      : Icons.trending_flat,
                              size: 16,
                              color: metrics.trend == 'improving'
                                  ? AppColors.statusTaken
                                  : metrics.trend == 'declining'
                                      ? AppColors.statusMissed
                                      : AppColors.textSecondary,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'Trend: ${metrics.trend.toUpperCase()}',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: metrics.trend == 'improving'
                                    ? AppColors.statusTaken
                                    : metrics.trend == 'declining'
                                        ? AppColors.statusMissed
                                        : AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              const Divider(color: AppColors.border, height: 1),
              const SizedBox(height: 16),
              // Streaks Row
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _buildStatItem('Current Streak', '${metrics.currentStreak} days', Icons.local_fire_department, Colors.orange),
                  Container(width: 1, height: 36, color: AppColors.border),
                  _buildStatItem('Best Streak', '${metrics.bestStreak} days', Icons.emoji_events_outlined, Colors.amber),
                  Container(width: 1, height: 36, color: AppColors.border),
                  _buildStatItem('Expected Doses', '${metrics.expectedDoses}', Icons.calendar_today_outlined, AppColors.primary),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Dose Outcome Counters
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.border, width: 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Dose History Breakdown', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(child: _buildOutcomePill('Taken', metrics.totalTaken, AppColors.statusTaken)),
                  const SizedBox(width: 8),
                  Expanded(child: _buildOutcomePill('Missed', metrics.totalMissed, AppColors.statusMissed)),
                  const SizedBox(width: 8),
                  Expanded(child: _buildOutcomePill('Skipped', metrics.totalSkipped, AppColors.statusSkipped)),
                  const SizedBox(width: 8),
                  Expanded(child: _buildOutcomePill('Snoozed', metrics.totalSnoozed, AppColors.statusPending)),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Time-of-Day Breakdown
        if (metrics.timeSlotBreakdown.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border, width: 1),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Time-of-Day Compliance', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                const SizedBox(height: 14),
                for (final entry in metrics.timeSlotBreakdown.entries) ...[
                  _buildTimeSlotRow(entry.key, entry.value),
                  if (entry.key != metrics.timeSlotBreakdown.keys.last)
                    const SizedBox(height: 12),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Detected Patterns
        if (metrics.detectedPatterns.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border, width: 1),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(Icons.lightbulb_outline, size: 18, color: AppColors.primary),
                    SizedBox(width: 6),
                    Text('Detected Behavioral Patterns', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  ],
                ),
                const SizedBox(height: 12),
                for (final pattern in metrics.detectedPatterns)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('• ', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)),
                        Expanded(
                          child: Text(pattern, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildPeriodSelector(WidgetRef ref, String currentPeriod) {
    const periods = [
      ('7d', 'Past 7 Days'),
      ('14d', 'Past 14 Days'),
      ('30d', 'Past 30 Days'),
    ];

    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Row(
        children: periods.map((p) {
          final isSelected = p.$1 == currentPeriod;
          return Expanded(
            child: GestureDetector(
              onTap: () => ref.read(adherencePeriodProvider.notifier).state = p.$1,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: isSelected ? AppColors.primary : Colors.transparent,
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Center(
                  child: Text(
                    p.$2,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                      color: isSelected ? Colors.white : AppColors.textSecondary,
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildEscalationBanner(AdherenceMetricsResponse metrics) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.statusMissed.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.statusMissed.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber_rounded, color: AppColors.statusMissed, size: 20),
              const SizedBox(width: 8),
              const Text(
                'Clinical Escalation Triggered',
                style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.statusMissed, fontSize: 13),
              ),
            ],
          ),
          if (metrics.escalationReasons.isNotEmpty) ...[
            const SizedBox(height: 6),
            for (final r in metrics.escalationReasons)
              Padding(
                padding: const EdgeInsets.only(left: 28, top: 2),
                child: Text('• $r', style: const TextStyle(fontSize: 12, color: AppColors.statusMissed)),
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildStatItem(String label, String value, IconData icon, Color iconColor) {
    return Column(
      children: [
        Icon(icon, size: 20, color: iconColor),
        const SizedBox(height: 4),
        Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppColors.textPrimary)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 11, color: AppColors.textDisabled)),
      ],
    );
  }

  Widget _buildOutcomePill(String label, int count, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          Text('$count', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
          const SizedBox(height: 2),
          Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
        ],
      ),
    );
  }

  Widget _buildTimeSlotRow(String slot, TimeSlotBreakdown metrics) {
    final slotLabel = switch (slot.toLowerCase()) {
      'morning' => 'Morning (06:00 - 12:00)',
      'afternoon' => 'Afternoon (12:00 - 17:00)',
      'evening' => 'Evening (17:00 - 21:00)',
      'night' => 'Night (21:00 - 06:00)',
      _ => slot[0].toUpperCase() + slot.substring(1),
    };

    final rate = metrics.adherenceRate;
    final pct = rate != null ? rate / 100.0 : 0.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(slotLabel, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
            Text(
              rate != null ? '${rate.toStringAsFixed(0)}% (${metrics.totalTaken}/${metrics.totalExpected})' : 'No doses',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: rate != null ? _rateColor(rate) : AppColors.textDisabled,
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: pct,
            minHeight: 8,
            backgroundColor: AppColors.surfaceVariant,
            valueColor: AlwaysStoppedAnimation<Color>(_rateColor(rate)),
          ),
        ),
      ],
    );
  }

  Color _rateColor(double? rate) {
    if (rate == null) return AppColors.textDisabled;
    if (rate >= 80.0) return AppColors.statusTaken;
    if (rate >= 60.0) return AppColors.statusPending;
    return AppColors.statusMissed;
  }
}
