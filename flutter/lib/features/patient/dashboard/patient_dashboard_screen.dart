import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/router.dart';
import '../../../app/theme/app_colors.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/widgets/state_views.dart';
import '../../auth/domain/session.dart';
import '../../auth/state/auth_controller.dart';
import '../adherence/state/adherence_controller.dart';
import '../adherence/widgets/adherence_summary_card.dart';
import '../medications/state/today_schedule_controller.dart';
import '../medications/widgets/dose_log_sheet.dart';
import '../medications/widgets/dose_tile.dart';
import 'widgets/patient_background.dart';

class PatientDashboardScreen extends ConsumerWidget {
  const PatientDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final schedule = ref.watch(todayScheduleProvider);

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text(
          'MedAssist AI',
          style: TextStyle(
            fontWeight: FontWeight.w600,
            color: AppColors.primary,
            letterSpacing: -0.5,
          ),
        ),
        backgroundColor: AppColors.surface.withValues(alpha: 0.85),
        elevation: 0,
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(color: Colors.transparent),
          ),
        ),
        actions: [
          Stack(
            alignment: Alignment.center,
            children: [
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.notifications_none_rounded, color: AppColors.textSecondary),
              ),
              Positioned(
                top: 12,
                right: 12,
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: AppColors.primaryLight,
                    shape: BoxShape.circle,
                    border: Border.all(color: AppColors.surface, width: 2),
                  ),
                ),
              ),
            ],
          ),
          IconButton(
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
            icon: const Icon(Icons.logout_rounded, color: AppColors.textSecondary),
            tooltip: 'Sign out',
          ),
        ],
      ),
      body: PatientBackground(
        child: RefreshIndicator(
          onRefresh: () async {
            await Future.wait([
              ref.read(todayScheduleProvider.notifier).refresh(),
              ref.read(adherenceMetricsProvider.notifier).refresh(),
            ]);
          },
          child: switch (schedule) {
            AsyncValue(hasValue: true, :final value?) => _ScheduleBody(
                schedule: value,
                refreshing: schedule.isLoading,
              ),
            AsyncValue(hasError: true, :final error?) => ListView(
                children: [
                  SizedBox(
                    height: MediaQuery.sizeOf(context).height * 0.6,
                    child: ErrorView(
                      error: error,
                      onRetry: () => ref.read(todayScheduleProvider.notifier).refresh(),
                    ),
                  ),
                ],
              ),
            _ => const LoadingView(label: 'Loading today\'s schedule…'),
          },
        ),
      ),
    );
  }
}

class _ScheduleBody extends ConsumerWidget {
  const _ScheduleBody({required this.schedule, required this.refreshing});

  final TodayScheduleResponse schedule;
  final bool refreshing;

  Future<void> _log(BuildContext context, WidgetRef ref, TodayDoseResponse dose) async {
    final recorded = await showDoseLogSheet(context, dose: dose);
    if (recorded == true && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${dose.medicineName} recorded.'),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metrics = ref.watch(adherenceMetricsProvider);
    final logging = ref.watch(doseLogControllerProvider);

    final session = ref.watch(currentSessionProvider);

    return Scrollbar(
      thumbVisibility: false,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 120), // Extra bottom padding for spatial feel
      children: [
        if (session != null) ...[
          _PatientHeader(session: session),
          const SizedBox(height: 16),
        ],
        // Adherence. Rendered by `AdherenceSummaryCard`, which owns the no-data rule
        // agreed for a null `adherence_rate`. An inline version of this block read
        // `value.score`, `value.dosesTaken` and `value.dosesScheduled` — none of which
        // exist on `AdherenceMetricsResponse` — and had no null branch at all.
        switch (metrics) {
          AsyncValue(hasValue: true, :final value?) => AdherenceSummaryCard(
              metrics: value,
              refreshing: metrics.isLoading,
            ),
          AsyncValue(hasError: true, :final error?) => Card(
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: ErrorView(
                  error: error,
                  onRetry: () => ref.read(adherenceMetricsProvider.notifier).refresh(),
                ),
              ),
            ),
          _ => const Card(child: Padding(padding: EdgeInsets.all(24), child: LoadingView(label: 'Loading adherence…'))),
        },
        
        const SizedBox(height: 24),

        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Text(
              'Today\'s Schedule',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
            const Spacer(),
            Text(
              '${schedule.dosesTaken} of ${schedule.totalDoses} taken',
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          '${schedule.localDate} · ${schedule.timezone}',
          style: const TextStyle(
            fontSize: 12,
            color: AppColors.textDisabled,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 12),

        if (schedule.doses.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: _EmptyScheduleState(),
          )
        else
          ...schedule.doses.map(
            (dose) => DoseTile(
              dose: dose,
              submitting: logging.isSubmitting(dose.scheduleId),
              onOpen: () => context.go(AppRoutes.patientDoseOf(dose.scheduleId)),
              onLog: () => _log(context, ref, dose),
            ),
          ),

        if (schedule.dosesRemaining > 0) ...[
          const SizedBox(height: 16),
          Center(
            child: Text(
              '${schedule.dosesRemaining} dose${schedule.dosesRemaining == 1 ? '' : 's'} not logged yet.',
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ],
    ));
  }
}


/// The dashboard body content without Scaffold/AppBar, for embedding
/// inside PatientShellScreen.
class PatientDashboardBody extends ConsumerWidget {
  const PatientDashboardBody({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final schedule = ref.watch(todayScheduleProvider);

    return PatientBackground(
      child: RefreshIndicator(
        onRefresh: () async {
          await Future.wait([
            ref.read(todayScheduleProvider.notifier).refresh(),
            ref.read(adherenceMetricsProvider.notifier).refresh(),
          ]);
        },
        child: switch (schedule) {
          AsyncValue(hasValue: true, :final value?) => _ScheduleBody(
              schedule: value,
              refreshing: schedule.isLoading,
            ),
          AsyncValue(hasError: true, :final error?) => ListView(
              children: [
                SizedBox(
                  height: MediaQuery.sizeOf(context).height * 0.6,
                  child: ErrorView(
                    error: error,
                    onRetry: () =>
                        ref.read(todayScheduleProvider.notifier).refresh(),
                  ),
                ),
              ],
            ),
          _ => const LoadingView(label: 'Loading schedule...'),
        },
      ),
    );
  }
}

class _PatientHeader extends StatelessWidget {
  const _PatientHeader({required this.session});

  final Session session;

  String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.outlineLight.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.surfaceVariant,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.primary.withValues(alpha: 0.4)),
                ),
                alignment: Alignment.center,
                child: Text(
                  _initials(session.displayName),
                  style: const TextStyle(
                    color: AppColors.primary,
                    fontWeight: FontWeight.w600,
                    fontSize: 16,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Good morning, ${session.displayName}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                      fontSize: 16,
                    ),
                  ),
                  const Text(
                    'ID: #PT-8402',
                    style: TextStyle(
                      fontFamily: 'JetBrains Mono',
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ],
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.primary.withValues(alpha: 0.3)),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: AppColors.primaryLight,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Text(
                      'SYNCED',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.5,
                        color: AppColors.primary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Connected to MedAssist Backend',
                style: TextStyle(
                  fontSize: 10,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _EmptyScheduleState extends StatelessWidget {
  const _EmptyScheduleState();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.outlineLight.withValues(alpha: 0.7),
          style: BorderStyle.solid,
        ),
      ),
      child: Column(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(
              color: AppColors.surfaceVariant,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.event_available, color: AppColors.primary),
          ),
          const SizedBox(height: 8),
          const Text(
            'Up To Date Schedule',
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: AppColors.textPrimary,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'No other doses scheduled today — All active prescriptions are up to date.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}
