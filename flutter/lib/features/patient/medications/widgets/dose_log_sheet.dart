import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/api_exception.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../shared/dose_status.dart';
import '../../../../shared/skip_reason_labels.dart';
import '../../adherence/state/adherence_controller.dart';

Future<bool?> showDoseLogSheet(
  BuildContext context, {
  required TodayDoseResponse dose,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: Colors.transparent,
    elevation: 0,
    builder: (context) => ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(alpha: 0.85),
            border: Border.all(color: AppColors.surface.withValues(alpha: 0.6), width: 1.5),
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: DoseLogSheet(dose: dose),
        ),
      ),
    ),
  );
}

enum _Step { choose, skipReason, help }

class DoseLogSheet extends ConsumerStatefulWidget {
  const DoseLogSheet({super.key, required this.dose});

  final TodayDoseResponse dose;

  @override
  ConsumerState<DoseLogSheet> createState() => _DoseLogSheetState();
}

class _DoseLogSheetState extends ConsumerState<DoseLogSheet> {
  final _note = TextEditingController();

  _Step _step = _Step.choose;
  SkipReasonCode? _reason;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _submit({
    required DoseLogAction action,
    SkipReasonCode? reason,
  }) async {
    HapticFeedback.mediumImpact();
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(doseLogControllerProvider.notifier).log(
            scheduleId: widget.dose.scheduleId,
            action: action,
            reminderId: widget.dose.reminderId,
            skipReasonCode: reason,
            note: reason == null ? null : _note.text,
          );
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        top: 32,
        bottom: 24 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_error != null) _ErrorBanner(_error!),
          switch (_step) {
            _Step.choose => _ChooseStep(
                dose: widget.dose,
                submitting: _submitting,
                onTaken: () {
                  HapticFeedback.lightImpact();
                  _submit(action: DoseLogAction.taken);
                },
                onSkip: () {
                  HapticFeedback.lightImpact();
                  setState(() => _step = _Step.skipReason);
                },
                onMissed: () {
                  HapticFeedback.lightImpact();
                  _submit(action: DoseLogAction.missed);
                },
                onHelp: () {
                  HapticFeedback.selectionClick();
                  setState(() => _step = _Step.help);
                },
              ),
            _Step.skipReason => _SkipReasonStep(
                selected: _reason,
                note: _note,
                submitting: _submitting,
                onSelect: (reason) {
                  HapticFeedback.selectionClick();
                  setState(() => _reason = reason);
                },
                onBack: () {
                  HapticFeedback.selectionClick();
                  setState(() => _step = _Step.choose);
                },
                onConfirm: _reason == null
                    ? null
                    : () => _submit(
                          action: DoseLogAction.skipped,
                          reason: _reason,
                        ),
              ),
            _Step.help => _HelpStep(
                dose: widget.dose,
                onBack: () {
                  HapticFeedback.selectionClick();
                  setState(() => _step = _Step.choose);
                },
              ),
          },
        ],
      ),
    );
  }
}

class _ChooseStep extends StatelessWidget {
  const _ChooseStep({
    required this.dose,
    required this.submitting,
    required this.onTaken,
    required this.onSkip,
    required this.onMissed,
    required this.onHelp,
  });

  final TodayDoseResponse dose;
  final bool submitting;
  final VoidCallback onTaken;
  final VoidCallback onSkip;
  final VoidCallback onMissed;
  final VoidCallback onHelp;

  @override
  Widget build(BuildContext context) {
    final subtitle = [
      if (dose.strength != null) dose.strength!,
      'Scheduled ${formatLocalTime(dose.scheduledLocalTime)}',
    ].join(' · ');

    final instruction = [
      if (dose.relationToMeal != null) formatMealRelation(dose.relationToMeal),
      if (dose.instructions != null) dose.instructions!,
    ].where((part) => part.trim().isNotEmpty).join('. ');

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.primary.withValues(alpha: 0.1),
              ),
              child: const Icon(Icons.medication_rounded, color: AppColors.primary, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    dose.medicineName,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                  ),
                  Text(subtitle, style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),

        // AI Advisory Card
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.surfaceVariant.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(12),
            border: const Border(left: BorderSide(color: AppColors.primary, width: 4)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.auto_awesome, color: AppColors.primary, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'AI-Assisted Advisory',
                      style: TextStyle(fontWeight: FontWeight.w600, color: AppColors.textPrimary, fontSize: 14),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      instruction.isNotEmpty ? 'High confidence: $instruction' : 'High confidence: No special instructions for this dose.',
                      style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 32),
        ElevatedButton.icon(
          onPressed: submitting ? null : onTaken,
          icon: submitting
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                )
              : const Icon(Icons.check_circle_rounded),
          label: const Text('Log as Taken', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.primary,
            foregroundColor: Colors.white,
            minimumSize: const Size.fromHeight(56),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
            elevation: 0,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: submitting ? null : onSkip,
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                  side: const BorderSide(color: AppColors.border),
                ),
                child: const Text('Skip Dose', style: TextStyle(color: AppColors.textSecondary, fontWeight: FontWeight.w600)),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton(
                onPressed: submitting ? null : onMissed,
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                  side: const BorderSide(color: AppColors.border),
                ),
                child: const Text('Report Missed', style: TextStyle(color: AppColors.textSecondary, fontWeight: FontWeight.w600)),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        TextButton.icon(
          onPressed: submitting ? null : onHelp,
          icon: const Icon(Icons.help_outline_rounded, size: 20),
          label: const Text('I need help', style: TextStyle(fontWeight: FontWeight.w600)),
          style: TextButton.styleFrom(foregroundColor: AppColors.textSecondary),
        ),
        if (submitting) ...[
          const SizedBox(height: 16),
          const Center(child: CircularProgressIndicator(strokeWidth: 2.5)),
        ],
      ],
    );
  }
}

class _SkipReasonStep extends StatelessWidget {
  const _SkipReasonStep({
    required this.selected,
    required this.note,
    required this.submitting,
    required this.onSelect,
    required this.onBack,
    required this.onConfirm,
  });

  final SkipReasonCode? selected;
  final TextEditingController note;
  final bool submitting;
  final ValueChanged<SkipReasonCode> onSelect;
  final VoidCallback onBack;
  final VoidCallback? onConfirm;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Why was this dose skipped?', style: AppTypography.titleLarge),
        const SizedBox(height: 4),
        Text(
          'Choosing an answer here is what lets your clinician see the real reason. '
          'It is recorded as your own answer, not as a guess.',
          style: AppTypography.bodyMedium,
        ),
        const SizedBox(height: 16),
        Opacity(
          opacity: submitting ? 0.5 : 1,
          child: AbsorbPointer(
            absorbing: submitting,
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.surface.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.border),
              ),
              // `groupValue`/`onChanged` on RadioListTile were deprecated after
              // Flutter 3.32; the group state lives in a RadioGroup ancestor now.
              child: RadioGroup<SkipReasonCode>(
                groupValue: selected,
                onChanged: (value) {
                  if (value != null) onSelect(value);
                },
                child: Column(
                  children: [
                    for (final code in kSkipReasonOrder)
                      RadioListTile<SkipReasonCode>(
                        value: code,
                        title: Text(
                          code.patientLabel,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        activeColor: AppColors.primary,
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 4,
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: note,
          enabled: !submitting,
          maxLength: 255,
          maxLines: 3,
          minLines: 2,
          decoration: InputDecoration(
            labelText: 'Anything else? (optional)',
            helperText: 'Shown to your clinician, quoted as your own words.',
            filled: true,
            fillColor: AppColors.surface.withValues(alpha: 0.5),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.border)),
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.border)),
          ),
        ),
        const SizedBox(height: 24),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: submitting ? null : onBack,
                style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                child: const Text('Back'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: ElevatedButton(
                onPressed: submitting ? null : onConfirm,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: AppColors.textPrimary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: submitting
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white))
                    : const Text('Record skip'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _HelpStep extends StatelessWidget {
  const _HelpStep({required this.dose, required this.onBack});

  final TodayDoseResponse dose;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('About this dose', style: AppTypography.titleLarge),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            children: [
              _HelpRow(label: 'Medication', value: dose.medicineName),
              if (dose.strength != null) _HelpRow(label: 'Strength', value: dose.strength!),
              if (dose.dose != null) _HelpRow(label: 'Amount', value: dose.dose!),
              _HelpRow(label: 'Scheduled', value: formatLocalTime(dose.scheduledLocalTime)),
              if (dose.relationToMeal != null) _HelpRow(label: 'Timing', value: formatMealRelation(dose.relationToMeal)),
              if (dose.instructions != null) _HelpRow(label: 'Instructions', value: dose.instructions!),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.dangerSurface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.danger),
          ),
          child: const Text(
            'This app cannot contact your clinician for you yet. If something feels wrong — a reaction, or you are unsure whether you already took this dose — contact your clinician directly.',
            style: TextStyle(fontSize: 14, color: AppColors.danger, fontWeight: FontWeight.w500, height: 1.5),
          ),
        ),
        const SizedBox(height: 24),
        OutlinedButton(
          onPressed: onBack,
          style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
          child: const Text('Back'),
        ),
      ],
    );
  }
}

class _HelpRow extends StatelessWidget {
  const _HelpRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 104, child: Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary, fontWeight: FontWeight.w600))),
          Expanded(child: Text(value, style: const TextStyle(fontSize: 15, color: AppColors.textPrimary, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.dangerSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.danger),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline_rounded, size: 24, color: AppColors.danger),
          const SizedBox(width: 12),
          Expanded(child: Text('Not recorded: $message', style: const TextStyle(fontSize: 14, color: AppColors.danger, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}

String formatLocalTime(String hhmm) {
  final parts = hhmm.split(':');
  final hour = int.tryParse(parts.first);
  if (parts.length < 2 || hour == null) return hhmm;
  final minute = parts[1].padLeft(2, '0');
  final period = hour < 12 ? 'AM' : 'PM';
  final display = hour % 12 == 0 ? 12 : hour % 12;
  return '$display:$minute $period';
}

String formatMealRelation(String? wire) => switch (wire) {
      'BEFORE_MEAL' => 'Before food',
      'AFTER_MEAL' => 'After food',
      'WITH_MEAL' => 'With food',
      'EMPTY_STOMACH' => 'On an empty stomach',
      null => '',
      _ => wire.replaceAll('_', ' ').toLowerCase(),
    };
