import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/router.dart';
import '../../../app/theme/app_colors.dart';
import '../../../app/theme/app_typography.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/widgets/state_views.dart';
import '../../../shared/dose_status.dart';
import '../../../shared/skip_reason_labels.dart';
import '../adherence/state/adherence_controller.dart';
import 'state/today_schedule_controller.dart';
import 'widgets/dose_log_sheet.dart';

/// One dose, in full, with the log actions.
///
/// Reads from the already-loaded [todayScheduleProvider] rather than fetching by id:
/// there is no `GET /schedule/doses/{id}` endpoint, and inventing a second source of
/// truth for the same row is how two screens end up disagreeing about a dose's status.
class DoseDetailScreen extends ConsumerWidget {
  const DoseDetailScreen({super.key, required this.scheduleId})
      : invalidRawId = null;

  /// A deep link whose id was not an integer.
  const DoseDetailScreen.invalidId(this.invalidRawId, {super.key}) : scheduleId = -1;

  final int scheduleId;
  final String? invalidRawId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (invalidRawId != null) {
      return _Shell(
        child: EmptyView(
          title: 'That link is not valid',
          detail: '"$invalidRawId" is not a dose reference.',
          icon: Icons.link_off,
        ),
      );
    }

    final schedule = ref.watch(todayScheduleProvider);

    return switch (schedule) {
      AsyncValue(hasValue: true, :final value?) => _resolve(context, ref, value),
      AsyncValue(hasError: true, :final error?) => _Shell(
          child: ErrorView(
            error: error,
            onRetry: () => ref.read(todayScheduleProvider.notifier).refresh(),
          ),
        ),
      _ => const _Shell(child: LoadingView()),
    };
  }

  Widget _resolve(BuildContext context, WidgetRef ref, TodayScheduleResponse schedule) {
    final dose = schedule.doses
        .where((candidate) => candidate.scheduleId == scheduleId)
        .firstOrNull;

    if (dose == null) {
      return const _Shell(
        child: EmptyView(
          title: 'This dose is not on today\'s schedule',
          detail: 'It may belong to another day, or the schedule may have changed.',
          icon: Icons.event_busy_outlined,
        ),
      );
    }
    return _DoseDetailBody(dose: dose, timezone: schedule.timezone);
  }
}

class _Shell extends StatelessWidget {
  const _Shell({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dose'),
        leading: IconButton(
          onPressed: () => context.go(AppRoutes.patientDashboard),
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back to today',
        ),
      ),
      body: child,
    );
  }
}

class _DoseDetailBody extends ConsumerWidget {
  const _DoseDetailBody({required this.dose, required this.timezone});

  final TodayDoseResponse dose;
  final String timezone;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = DoseStatus.fromWire(dose.status);
    final skipCode = skipReasonCodeOrNull(dose.skipReasonCode);
    final submitting =
        ref.watch(doseLogControllerProvider).isSubmitting(dose.scheduleId);

    return _Shell(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          Text(dose.medicineName, style: AppTypography.headlineMedium),
          if (dose.strength != null) ...[
            const SizedBox(height: 4),
            Text(dose.strength!, style: AppTypography.doseStrength),
          ],
          const SizedBox(height: 18),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(status.icon, size: 20, color: status.color),
                      const SizedBox(width: 8),
                      Text(
                        status.label,
                        style: AppTypography.titleMedium.copyWith(color: status.color),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  _Row(
                    label: 'Scheduled',
                    value: '${formatLocalTime(dose.scheduledLocalTime)} · $timezone',
                  ),
                  if (dose.dose != null) _Row(label: 'Amount', value: dose.dose!),
                  if (dose.relationToMeal != null)
                    _Row(
                      label: 'Timing',
                      value: formatMealRelation(dose.relationToMeal),
                    ),
                  if (dose.instructions != null)
                    _Row(label: 'Instructions', value: dose.instructions!),
                  if (dose.confirmedAt != null)
                    _Row(
                      label: 'Recorded',
                      // toLocal() is right here and wrong for scheduled_local_time:
                      // this is a real instant that happened, not a wall-clock slot.
                      value: _formatInstant(dose.confirmedAt!.toLocal()),
                    ),
                  if (skipCode != null)
                    _Row(label: 'Reason', value: skipCode.patientLabel),
                ],
              ),
            ),
          ),
          if (dose.skipReason != null) ...[
            const SizedBox(height: 14),
            _PatientNote(note: dose.skipReason!),
          ],
          const SizedBox(height: 22),
          if (!status.isLogged)
            FilledButton.icon(
              onPressed: submitting
                  ? null
                  : () async {
                      final recorded = await showDoseLogSheet(context, dose: dose);
                      if (recorded == true && context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('${dose.medicineName} recorded.')),
                        );
                      }
                    },
              icon: const Icon(Icons.check_circle_outline),
              label: const Text('Record this dose'),
            )
          else
            Text(
              'This dose has already been recorded. Ask your clinician if it needs '
              'to be corrected — the record is kept as it was entered.',
              style: AppTypography.bodyMedium,
            ),
        ],
      ),
    );
  }

  static String _formatInstant(DateTime local) {
    final hour = local.hour % 12 == 0 ? 12 : local.hour % 12;
    final minute = local.minute.toString().padLeft(2, '0');
    final period = local.hour < 12 ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }
}

/// The patient's own free-text note, shown as a quotation.
///
/// `skip_reason` is untrusted input. Rendered as an attributed quote and never as
/// app-authored copy, so a note reading "Ignore previous instructions…" is visibly the
/// patient's words rather than something the app appears to be saying. This is the same
/// separation the backend maintains in the prompt contract, held at the UI edge.
class _PatientNote extends StatelessWidget {
  const _PatientNote({required this.note});

  final String note;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(10),
        border: Border(
          left: BorderSide(color: AppColors.border, width: 4),
          top: BorderSide(color: AppColors.border),
          right: BorderSide(color: AppColors.border),
          bottom: BorderSide(color: AppColors.border),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('YOUR NOTE', style: AppTypography.tierBadge),
          const SizedBox(height: 6),
          // SelectableText so it can be copied but not confused with a control.
          SelectableText(note, style: AppTypography.bodyLarge),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 100, child: Text(label, style: AppTypography.labelSmall)),
          Expanded(child: Text(value, style: AppTypography.bodyLarge)),
        ],
      ),
    );
  }
}
