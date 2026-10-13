import 'package:flutter/material.dart';
import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/api_exception.dart';

/// Bottom sheet for clinician dose-event corrections.
///
/// Shows the current event status, lets the clinician pick the corrected
/// status, type a mandatory clinical reason, and submit. Uses the
/// approved token system (no glassmorphism, no blur).
class DoseCorrectionSheet extends StatefulWidget {
  const DoseCorrectionSheet({
    super.key,
    required this.eventId,
    required this.currentStatus,
    required this.medicineName,
    required this.onCorrect,
  });

  final int eventId;
  final String currentStatus;
  final String medicineName;
  final Future<void> Function({
    required int eventId,
    required String newStatus,
    required String reason,
  }) onCorrect;

  @override
  State<DoseCorrectionSheet> createState() => _DoseCorrectionSheetState();
}

class _DoseCorrectionSheetState extends State<DoseCorrectionSheet> {
  final _reasonController = TextEditingController();
  String? _selectedStatus;
  bool _submitting = false;
  String? _error;

  static const _statuses = ['TAKEN', 'SKIPPED', 'MISSED'];

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final trimmedReason = _reasonController.text.trim();
    if (_selectedStatus == null) {
      setState(() => _error = 'Select a corrected status.');
      return;
    }
    if (trimmedReason.length < 3) {
      setState(() => _error = 'Reason must be at least 3 characters.');
      return;
    }
    if (trimmedReason.length > 255) {
      setState(() => _error = 'Reason cannot exceed 255 characters.');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.onCorrect(
        eventId: widget.eventId,
        newStatus: _selectedStatus!,
        reason: trimmedReason,
      );
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _submitting = false;
          _error = e.message;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _submitting = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Drag handle
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.border,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 16),
          // Title
          Text('Correct Dose Event', style: AppTypography.titleLarge),
          const SizedBox(height: 4),
          Text(
            widget.medicineName,
            style: AppTypography.bodyMedium.copyWith(
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          // Current status
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              children: [
                const Text(
                  'CURRENT STATUS',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(width: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceVariant,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Text(
                    widget.currentStatus,
                    style: const TextStyle(
                      fontFamily: 'JetBrains Mono',
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // Status picker
          const Text(
            'CORRECTED STATUS',
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: _statuses
                .where((s) => s != widget.currentStatus)
                .map((s) => Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        child: ChoiceChip(
                          label: Text(
                            s,
                            style: TextStyle(
                              fontFamily: 'JetBrains Mono',
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: _selectedStatus == s
                                  ? AppColors.surface
                                  : AppColors.textPrimary,
                            ),
                          ),
                          selected: _selectedStatus == s,
                          selectedColor: AppColors.primary,
                          backgroundColor: AppColors.surfaceVariant,
                          side: BorderSide(
                            color: _selectedStatus == s
                                ? AppColors.primary
                                : AppColors.border,
                          ),
                          onSelected: (_) =>
                              setState(() => _selectedStatus = s),
                        ),
                      ),
                    ))
                .toList(),
          ),
          const SizedBox(height: 16),
          // Reason field
          const Text(
            'CLINICAL REASON (REQUIRED)',
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _reasonController,
            maxLines: 3,
            maxLength: 255,
            style: AppTypography.bodyMedium.copyWith(
              color: AppColors.textPrimary,
            ),
            decoration: InputDecoration(
              hintText: 'e.g. Patient confirmed dose was taken but not logged.',
              hintStyle: AppTypography.bodyMedium.copyWith(
                color: AppColors.textDisabled,
              ),
              filled: true,
              fillColor: AppColors.surfaceMuted,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: AppColors.border),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: AppColors.border),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
              ),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(
              _error!,
              style: AppTypography.bodyMedium.copyWith(color: AppColors.danger),
            ),
          ],
          const SizedBox(height: 20),
          // Actions
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _submitting ? null : () => Navigator.of(context).pop(),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.textPrimary,
                    backgroundColor: AppColors.surfaceVariant,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    side: const BorderSide(color: AppColors.border),
                  ),
                  child: const Text('Cancel', style: TextStyle(fontWeight: FontWeight.w600)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  onPressed: _submitting ? null : _submit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: AppColors.surface,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: _submitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: AppColors.surface,
                          ),
                        )
                      : const Text(
                          'Apply Correction',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
