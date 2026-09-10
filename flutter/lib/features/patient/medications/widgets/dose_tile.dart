import 'package:flutter/material.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../shared/dose_status.dart';

class DoseTile extends StatelessWidget {
  const DoseTile({
    super.key,
    required this.dose,
    required this.onOpen,
    required this.onLog,
    this.submitting = false,
  });

  final TodayDoseResponse dose;
  final VoidCallback onOpen;
  final VoidCallback onLog;
  final bool submitting;

  @override
  Widget build(BuildContext context) {
    final status = DoseStatus.fromWire(dose.status);
    final isPending = status == DoseStatus.pending || status == DoseStatus.unknown;
    final isTaken = status == DoseStatus.taken;
    final isSkipped = status == DoseStatus.skipped || status == DoseStatus.snoozed;
    final isMissed = status == DoseStatus.missed;

    // Use specific colors from the design
    final accentColor = isTaken
        ? const Color(0xFF34D399) // emerald-400
        : isSkipped
            ? const Color(0xFFFBBF24) // amber-400
            : isMissed
                ? const Color(0xFFF43F5E) // rose-500
                : AppColors.primary;

    final badgeBg = isTaken
        ? const Color(0xFF10B981).withValues(alpha: 0.15)
        : isSkipped
            ? const Color(0xFFF59E0B).withValues(alpha: 0.15)
            : isMissed
                ? const Color(0xFFF43F5E).withValues(alpha: 0.15)
                : Colors.transparent;

    final badgeBorder = isTaken
        ? const Color(0xFF10B981)
        : isSkipped
            ? const Color(0xFFF59E0B)
            : isMissed
                ? const Color(0xFFF43F5E)
                : Colors.grey.shade500;

    final badgeText = isTaken
        ? const Color(0xFF6EE7B7) // emerald-300
        : isSkipped
            ? const Color(0xFFFCD34D) // amber-300
            : isMissed
                ? const Color(0xFFFDA4AF) // rose-300
                : Colors.grey.shade300;

    final instruction = [
      if (dose.relationToMeal != null) formatMealRelation(dose.relationToMeal),
      if (dose.instructions != null) dose.instructions!,
    ].where((part) => part.trim().isNotEmpty).join(' · ');

    return GestureDetector(
      onTap: onOpen,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          color: isPending
              ? AppColors.surfaceVariant.withValues(alpha: 0.8)
              : AppColors.surface.withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isPending ? AppColors.primary.withValues(alpha: 0.5) : AppColors.outlineLight.withValues(alpha: 0.6),
          ),
          boxShadow: isPending
              ? [
                  BoxShadow(
                    color: AppColors.primary.withValues(alpha: 0.2),
                    blurRadius: 0,
                    spreadRadius: 1, // ring-1 ring-primary/20
                  )
                ]
              : null,
        ),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Left Accent Line
              Container(width: 4, color: accentColor),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Row(
                            children: [
                              Text(
                                dose.medicineName,
                                style: TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 16,
                                  color: isTaken ? AppColors.primary : AppColors.textPrimary,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: AppColors.surfaceVariant,
                                  borderRadius: BorderRadius.circular(4),
                                  border: Border.all(color: AppColors.outlineLight.withValues(alpha: 0.4)),
                                ),
                                child: Text(
                                  dose.strength ?? '',
                                  style: const TextStyle(
                                    fontFamily: 'JetBrains Mono',
                                    fontSize: 12,
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: badgeBg,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: badgeBorder),
                            ),
                            child: Text(
                              status.wire.toUpperCase().isNotEmpty ? status.wire.toUpperCase() : 'PENDING',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.5,
                                color: badgeText,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Row(
                            children: [
                              Icon(
                                isMissed ? Icons.event_busy : Icons.schedule,
                                size: 16,
                                color: isMissed
                                    ? Colors.red.shade400
                                    : isPending
                                        ? AppColors.primary
                                        : AppColors.textSecondary,
                              ),
                              const SizedBox(width: 6),
                              Text(
                                isMissed
                                    ? 'Yesterday ${formatLocalTime(dose.scheduledLocalTime)}'
                                    : formatLocalTime(dose.scheduledLocalTime),
                                style: TextStyle(
                                  fontFamily: 'JetBrains Mono',
                                  fontSize: 13,
                                  fontWeight: isPending ? FontWeight.w600 : FontWeight.w500,
                                  color: isMissed
                                      ? Colors.red.shade300
                                      : isPending
                                          ? AppColors.primary
                                          : AppColors.textPrimary,
                                ),
                              ),
                              if (instruction.isNotEmpty) ...[
                                const Padding(
                                  padding: EdgeInsets.symmetric(horizontal: 6),
                                  child: Text('•', style: TextStyle(color: AppColors.textDisabled)),
                                ),
                                Text(
                                  instruction,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ],
                            ],
                          ),
                          if (isTaken)
                            const Row(
                              children: [
                                Text(
                                  'DETAILS',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 0.5,
                                    color: AppColors.primary,
                                  ),
                                ),
                                Icon(Icons.chevron_right, size: 16, color: AppColors.primary),
                              ],
                            ),
                          if (isMissed)
                            const Text(
                              'Report Miss',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.5,
                                color: AppColors.primary,
                                decoration: TextDecoration.underline,
                              ),
                            ),
                        ],
                      ),
                      if (isSkipped && dose.skipReason != null) ...[
                        const SizedBox(height: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.amber.shade900.withValues(alpha: 0.4),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: Colors.amber.shade800.withValues(alpha: 0.4)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.report_problem, size: 12, color: Colors.amber),
                              const SizedBox(width: 6),
                              Text(
                                'Reason logged: ${dose.skipReason}',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Colors.amber.shade200.withValues(alpha: 0.8),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                      if (isPending) ...[
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: ElevatedButton.icon(
                                onPressed: submitting ? null : onLog,
                                icon: submitting
                                    ? const SizedBox(
                                        width: 16,
                                        height: 16,
                                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                                      )
                                    : const Icon(Icons.check_circle, size: 16),
                                label: const Text(
                                  'Log Dose',
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: AppColors.primaryLight,
                                  foregroundColor: AppColors.textOnPrimary,
                                  elevation: 0,
                                  padding: const EdgeInsets.symmetric(vertical: 12),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            OutlinedButton(
                              onPressed: () {},
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppColors.textSecondary,
                                side: const BorderSide(color: AppColors.outlineLight),
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              child: const Text('Skip', style: TextStyle(fontSize: 12)),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String formatLocalTime(String iso) {
  try {
    final dt = DateTime.parse(iso);
    final hr = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
    final ampm = dt.hour >= 12 ? 'PM' : 'AM';
    final min = dt.minute.toString().padLeft(2, '0');
    return '$hr:$min $ampm';
  } catch (_) {
    return iso;
  }
}

String formatMealRelation(String? relation) {
  if (relation == null) return '';
  return relation.replaceAll('_', ' ').toLowerCase();
}


