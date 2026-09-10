import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/widgets/state_views.dart';
import 'state/adherence_analysis_provider.dart';
import 'widgets/all_clear_view.dart';
import 'widgets/finding_present_view.dart';

final simulationStateProvider = StateProvider<bool?>((ref) => null);

class ClinicianDashboardScreen extends ConsumerWidget {
  const ClinicianDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Hardcoding patient 1 for demo purposes
    final analysisAsync = ref.watch(adherenceAnalysisProvider(1));
    final simulationState = ref.watch(simulationStateProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
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
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
          onPressed: () {},
        ),
        actions: [
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.notifications_none_rounded, color: AppColors.textSecondary),
          ),
        ],
        backgroundColor: AppColors.surface.withValues(alpha: 0.85),
        elevation: 0,
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Container(
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: AppColors.border, width: 1)),
              ),
            ),
          ),
        ),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 430),
          child: Container(
            decoration: const BoxDecoration(
              color: AppColors.surface,
              border: Border.symmetric(
                vertical: BorderSide(color: AppColors.border, width: 1),
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black26,
                  blurRadius: 24,
                  spreadRadius: 1,
                ),
              ],
            ),
            child: SafeArea(
              child: switch (analysisAsync) {
                AsyncValue(hasValue: true, :final value?) => _buildContent(context, ref, value, simulationState),
                AsyncValue(hasError: true, :final error?) => ErrorView(
                    error: error,
                    onRetry: () => ref.refresh(adherenceAnalysisProvider(1).future),
                  ),
                _ => const LoadingView(label: 'Evaluating patient safety...'),
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildContent(
    BuildContext context,
    WidgetRef ref,
    AdherenceAnalysisResult analysis,
    bool? simulationState,
  ) {
    // If simulationState is not null, use it. Otherwise, derive from actual data.
    final bool isFindingPresent = simulationState ?? (analysis.safetyRiskLevel != 'NONE');

    return RefreshIndicator(
      onRefresh: () async => ref.refresh(adherenceAnalysisProvider(1).future),
      child: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        children: [
          _buildHeader(analysis),
          const SizedBox(height: 16),
          _buildStateSwitcher(ref, isFindingPresent),
          const SizedBox(height: 24),
          if (isFindingPresent)
            FindingPresentView(analysis: analysis)
          else
            AllClearView(analysis: analysis),
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
                  'PID: #JD-${analysis.patientId}',
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
          RichText(
            text: const TextSpan(
              style: TextStyle(fontSize: 14, color: AppColors.textSecondary),
              children: [
                TextSpan(text: 'Patient: '),
                TextSpan(text: 'Jane Doe', style: TextStyle(fontWeight: FontWeight.w500, color: AppColors.textPrimary)),
                TextSpan(text: ' (42y • Female)'),
              ],
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

  Widget _buildStateSwitcher(WidgetRef ref, bool isFindingPresent) {
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              onTap: () => ref.read(simulationStateProvider.notifier).state = true,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: isFindingPresent ? const Color(0xFFFFDAD6) : Colors.transparent,
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: isFindingPresent
                      ? [BoxShadow(color: Colors.black.withValues(alpha: 0.1), blurRadius: 4)]
                      : null,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.warning_amber_rounded,
                      size: 16,
                      color: isFindingPresent ? const Color(0xFFBA1A1A) : AppColors.textSecondary,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'State A: Finding-Present',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: isFindingPresent ? const Color(0xFFBA1A1A) : AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          Expanded(
            child: GestureDetector(
              onTap: () => ref.read(simulationStateProvider.notifier).state = false,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: !isFindingPresent ? const Color(0x3310B981) : Colors.transparent,
                  borderRadius: BorderRadius.circular(6),
                  border: !isFindingPresent ? Border.all(color: const Color(0x8010B981)) : null,
                  boxShadow: !isFindingPresent
                      ? [BoxShadow(color: Colors.black.withValues(alpha: 0.1), blurRadius: 4)]
                      : null,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.check_circle_outline,
                      size: 16,
                      color: !isFindingPresent ? const Color(0xFF6EE7B7) : AppColors.textSecondary,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'State B: All Clear Calm',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: !isFindingPresent ? const Color(0xFF6EE7B7) : AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
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
}
