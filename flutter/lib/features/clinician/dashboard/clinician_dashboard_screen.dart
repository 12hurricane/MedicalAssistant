import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/api/api_exception.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/widgets/state_views.dart';
import 'data/clinician_dose_repository.dart';
import 'state/adherence_analysis_provider.dart';
import 'state/clinician_doses_provider.dart';
import 'widgets/all_clear_view.dart';
import 'widgets/dose_correction_sheet.dart';
import 'widgets/finding_present_view.dart';

class ClinicianDashboardScreen extends ConsumerWidget {
  const ClinicianDashboardScreen({
    super.key,
    required this.patientId,
  }) : invalidRawId = null;

  /// A route whose patientId parameter was not an integer or was missing.
  const ClinicianDashboardScreen.invalidId(
    this.invalidRawId, {
    super.key,
  }) : patientId = -1;

  final int patientId;
  final String? invalidRawId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (invalidRawId != null) {
      return Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          title: const Text(
            'Clinical Review & Safety Analysis',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: AppColors.primary,
              letterSpacing: -0.5,
            ),
          ),
          centerTitle: true,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
            onPressed: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/clinician');
              }
            },
          ),
          backgroundColor: AppColors.surface,
          elevation: 0,
          shape: const Border(bottom: BorderSide(color: AppColors.border, width: 1)),
        ),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 600),
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 32),
              children: [
                EmptyView(
                  title: 'Invalid Patient Link',
                  detail: invalidRawId!.isEmpty
                      ? 'No patient ID was provided in the route.'
                      : '"$invalidRawId" is not a valid patient reference.',
                  icon: Icons.link_off,
                ),
              ],
            ),
          ),
        ),
      );
    }

    final analysisAsync = ref.watch(adherenceAnalysisProvider(patientId));

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          'Clinical Review & Safety Analysis',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: AppColors.primary,
            letterSpacing: -0.5,
          ),
        ),
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go('/clinician');
            }
          },
        ),
        actions: [
          IconButton(
            onPressed: () {
              ref.invalidate(adherenceAnalysisProvider(patientId));
              ref.invalidate(clinicianDosesProvider(patientId));
            },
            icon: const Icon(Icons.refresh, color: AppColors.textSecondary),
            tooltip: 'Re-evaluate patient',
          ),
        ],
        backgroundColor: AppColors.surface,
        elevation: 0,
        shape: const Border(bottom: BorderSide(color: AppColors.border, width: 1)),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 600),
          child: Container(
            decoration: const BoxDecoration(
              color: AppColors.surface,
              border: Border.symmetric(
                vertical: BorderSide(color: AppColors.border, width: 1),
              ),
            ),
            child: SafeArea(
              child: switch (analysisAsync) {
                AsyncValue(hasValue: true, :final value?) =>
                  _buildContent(context, ref, value),
                AsyncValue(hasError: true, :final error?)
                    when error is ForbiddenException =>
                  _buildAccessDenied(context),
                AsyncValue(hasError: true, :final error?) => ErrorView(
                    error: error,
                    onRetry: () {
                      ref.invalidate(adherenceAnalysisProvider(patientId));
                      ref.invalidate(clinicianDosesProvider(patientId));
                    },
                  ),
                _ => const LoadingView(label: 'Evaluating patient safety...'),
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAccessDenied(BuildContext context) {
    return ListView(
      children: const [
        SizedBox(height: 100),
        _AccessDeniedView(),
      ],
    );
  }

  Widget _buildContent(
    BuildContext context,
    WidgetRef ref,
    AdherenceAnalysisResult analysis,
  ) {
    final bool isFindingPresent =
        analysis.safetyRiskLevel.toUpperCase() != 'LOW' || analysis.requiresHumanReview;

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(adherenceAnalysisProvider(patientId));
        ref.invalidate(clinicianDosesProvider(patientId));
      },
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        children: [
          _buildHeader(analysis),
          const SizedBox(height: 24),
          if (isFindingPresent)
            FindingPresentView(analysis: analysis)
          else
            AllClearView(analysis: analysis),
          const SizedBox(height: 24),
          _buildDoseEventsSection(context, ref, patientId),
          const SizedBox(height: 80), // Padding for bottom nav area
        ],
      ),
    );
  }

  Widget _buildHeader(AdherenceAnalysisResult analysis) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      color: AppColors.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 6),
                  const Text(
                    'ACTIVE SESSION',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 0.5,
                      color: AppColors.primary,
                    ),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.surfaceVariant,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: AppColors.border.withValues(alpha: 0.4)),
                ),
                child: Text(
                  'PID: #${analysis.patientId}',
                  style: const TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const Text(
            'Clinical Safety & Analysis',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w600,
              letterSpacing: -0.5,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            'Patient #${analysis.patientId}',
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.only(top: 12),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: AppColors.border.withValues(alpha: 0.4))),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    const Icon(Icons.verified, size: 16, color: AppColors.primary),
                    const SizedBox(width: 4),
                    Text(
                      'Evaluated: Today at ${_formatTime(analysis.evaluatedAt)}',
                      style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                    ),
                  ],
                ),
                Text(
                  'Rule Engine v4.2',
                  style: TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 10,
                    color: AppColors.textSecondary.withValues(alpha: 0.8),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime time) {
    final hour = time.hour == 0 ? 12 : (time.hour > 12 ? time.hour - 12 : time.hour);
    final minute = time.minute.toString().padLeft(2, '0');
    final amPm = time.hour >= 12 ? 'PM' : 'AM';
    return '$hour:$minute $amPm';
  }

  Widget _buildDoseEventsSection(
    BuildContext context,
    WidgetRef ref,
    int patientId,
  ) {
    final dosesAsync = ref.watch(clinicianDosesProvider(patientId));

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Row(
                children: [
                  Icon(Icons.medication_outlined, size: 18, color: AppColors.primary),
                  SizedBox(width: 8),
                  Text(
                    "Today's Medication Doses",
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ],
              ),
              IconButton(
                icon: const Icon(Icons.refresh, size: 16, color: AppColors.textSecondary),
                onPressed: () => ref.refresh(clinicianDosesProvider(patientId).future),
                tooltip: 'Refresh doses',
              ),
            ],
          ),
          const SizedBox(height: 12),
          switch (dosesAsync) {
            AsyncValue(hasValue: true, :final value?) =>
              _buildDoseList(context, ref, patientId, value),
            AsyncValue(hasError: true, :final error?)
                when error is ForbiddenException =>
              const Text(
                'Access to dose schedule denied.',
                style: TextStyle(color: AppColors.danger, fontSize: 13),
              ),
            AsyncValue(hasError: true, :final error?) => Row(
                children: [
                  Expanded(
                    child: Text(
                      'Failed to load doses: ${error.toString()}',
                      style: const TextStyle(color: AppColors.danger, fontSize: 13),
                    ),
                  ),
                  TextButton(
                    onPressed: () => ref.refresh(clinicianDosesProvider(patientId).future),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            _ => const Padding(
                padding: EdgeInsets.all(16),
                child: Center(
                  child: Text(
                    'Loading doses...',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
              ),
          },
        ],
      ),
    );
  }

  Widget _buildDoseList(
    BuildContext context,
    WidgetRef ref,
    int patientId,
    TodayScheduleResponse schedule,
  ) {
    if (schedule.doses.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Text(
          'No scheduled doses for today.',
          style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
        ),
      );
    }

    return Column(
      children: schedule.doses.map((dose) {
        final bool canCorrect = dose.eventId != null;
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      dose.medicineName,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Scheduled: ${dose.scheduledLocalTime}${dose.dose != null ? ' • ${dose.dose}' : ''}',
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    if (dose.skipReason != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        'Reason: "${dose.skipReason}"',
                        style: const TextStyle(
                          fontSize: 11,
                          fontStyle: FontStyle.italic,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              _buildStatusBadge(dose.status),
              if (canCorrect) ...[
                const SizedBox(width: 8),
                TextButton(
                  key: Key('correct_dose_button_${dose.eventId}'),
                  onPressed: () => _openCorrectionSheet(context, ref, patientId, dose),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    backgroundColor: AppColors.surfaceVariant,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(6),
                      side: const BorderSide(color: AppColors.border),
                    ),
                  ),
                  child: const Text(
                    'Correct',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ],
          ),
        );
      }).toList(),
    );
  }

  Widget _buildStatusBadge(String status) {
    Color bg;
    Color fg;
    switch (status.toUpperCase()) {
      case 'TAKEN':
        bg = const Color(0x3310B981);
        fg = const Color(0xFF10B981);
        break;
      case 'SKIPPED':
        bg = const Color(0x33F59E0B);
        fg = const Color(0xFFF59E0B);
        break;
      case 'MISSED':
        bg = const Color(0x33EF4444);
        fg = const Color(0xFFEF4444);
        break;
      default:
        bg = AppColors.surfaceVariant;
        fg = AppColors.textSecondary;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        status.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          fontFamily: 'JetBrains Mono',
          color: fg,
        ),
      ),
    );
  }

  Future<void> _openCorrectionSheet(
    BuildContext context,
    WidgetRef ref,
    int patientId,
    TodayDoseResponse dose,
  ) async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => DoseCorrectionSheet(
        eventId: dose.eventId!,
        currentStatus: dose.status,
        medicineName: dose.medicineName,
        onCorrect: ({required eventId, required newStatus, required reason}) async {
          await ref.read(clinicianDoseRepositoryProvider).correctEvent(
                eventId: eventId,
                newStatus: newStatus,
                reason: reason,
              );
        },
      ),
    );

    if (result == true && context.mounted) {
      ref.invalidate(clinicianDosesProvider(patientId));
      ref.invalidate(adherenceAnalysisProvider(patientId));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Dose event corrected successfully.'),
          duration: Duration(seconds: 3),
        ),
      );
    }
  }
}

/// Controlled display for a 403 response on clinical analysis.
///
/// The backend is the authorization authority. A 403 here means the
/// authenticated clinician is not permitted to review this patient —
/// retrying will not help, and the UI must not suggest otherwise.
class _AccessDeniedView extends StatelessWidget {
  const _AccessDeniedView();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: AppColors.statusMissed.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.shield_outlined,
                size: 32,
                color: AppColors.statusMissed,
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Access Denied',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'You do not have permission to view this patient\'s clinical analysis. '
              'Contact your administrator if you believe this is an error.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 14,
                color: AppColors.textSecondary,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
