import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:go_router/go_router.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/api/generated/api_models.dart';
import '../../../../core/providers.dart';

class PrescriptionUploadScreen extends ConsumerStatefulWidget {
  const PrescriptionUploadScreen({super.key});

  @override
  ConsumerState<PrescriptionUploadScreen> createState() =>
      _PrescriptionUploadScreenState();
}

class _PrescriptionUploadScreenState
    extends ConsumerState<PrescriptionUploadScreen> {
  final ImagePicker _picker = ImagePicker();
  bool _isLoading = false;
  String? _error;
  PrescriptionResponse? _parsedResult;

  Future<void> _pickAndUpload(ImageSource source) async {
    try {
      final XFile? image = await _picker.pickImage(
        source: source,
        maxWidth: 1600,
        maxHeight: 1600,
        imageQuality: 85,
      );
      if (image == null) return;

      setState(() {
        _isLoading = true;
        _error = null;
        _parsedResult = null;
      });

      final bytes = await image.readAsBytes();
      final base64Image = base64Encode(bytes);

      final client = ref.read(apiClientProvider);
      final prescription = await client.postObject<PrescriptionResponse>(
        ApiEndpoints.uploadPrescription,
        body: {'image_base64': base64Image},
        decode: PrescriptionResponse.fromJson,
      );

      if (mounted) {
        setState(() {
          _parsedResult = prescription;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: AppColors.accent,
            content: Text(
              'Prescription processed successfully via AI orchestration!',
              style: TextStyle(color: Colors.white),
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Digitize Prescription', style: AppTypography.titleLarge),
        backgroundColor: AppColors.surface,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: AppColors.textPrimary),
          onPressed: () => context.pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppColors.border),
              ),
              child: Column(
                children: [
                  Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      color: AppColors.primaryDark.withValues(alpha: 0.3),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.document_scanner_outlined,
                      size: 36,
                      color: AppColors.primary,
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'AI Prescription Ingestion',
                    style: AppTypography.titleMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Upload or capture a photo of your physical prescription. Our multi-agent AI automatically extracts medications, parses dosages, and validates safety.',
                    textAlign: TextAlign.center,
                    style: AppTypography.bodyMedium,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            if (_isLoading) ...[
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppColors.border),
                ),
                child: const Column(
                  children: [
                    CircularProgressIndicator(color: AppColors.primary),
                    SizedBox(height: 16),
                    Text(
                      'Running OCR & Clinical Safety Analysis...',
                      style: AppTypography.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                    SizedBox(height: 6),
                    Text(
                      'Extracting text -> Structuring schema -> Checking interactions',
                      style: AppTypography.bodyMedium,
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ] else ...[
              ElevatedButton.icon(
                onPressed: () => _pickAndUpload(ImageSource.camera),
                icon: const Icon(Icons.camera_alt, color: AppColors.textOnPrimary),
                label: const Text(
                  'Take Photo with Camera',
                  style: TextStyle(
                    color: AppColors.textOnPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  minimumSize: const Size(double.infinity, 50),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () => _pickAndUpload(ImageSource.gallery),
                icon: const Icon(Icons.photo_library, color: AppColors.textPrimary),
                label: const Text(
                  'Select from Gallery',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(double.infinity, 50),
                  side: const BorderSide(color: AppColors.outlineLight),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.dangerSurface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.danger.withValues(alpha: 0.5)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: AppColors.danger),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        _error!,
                        style: AppTypography.bodyMedium.copyWith(color: AppColors.danger),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (_parsedResult != null) ...[
              const SizedBox(height: 24),
              _buildExtractedSummaryCard(_parsedResult!),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildExtractedSummaryCard(PrescriptionResponse rx) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.check_circle, color: AppColors.accent, size: 24),
              const SizedBox(width: 10),
              Text(
                'Prescription #${rx.id} Extracted',
                style: AppTypography.titleMedium.copyWith(color: AppColors.accent),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.surfaceMuted,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  rx.verificationStatus,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: AppColors.primaryLight,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (rx.doctorName != null)
            Text('Doctor: ${rx.doctorName}', style: AppTypography.bodyLarge),
          if (rx.clinicName != null)
            Text('Clinic: ${rx.clinicName}', style: AppTypography.bodyMedium),
          Text(
            'Prescription Date: ${rx.prescriptionDate.toIso8601String().split('T')[0]}',
            style: AppTypography.bodyMedium,
          ),
          const Divider(color: AppColors.border, height: 24),
          const Text('Extracted Medications:', style: AppTypography.titleMedium),
          const SizedBox(height: 8),
          ...rx.medications.map(
            (m) => Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(Icons.medication_outlined, color: AppColors.primary),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${m.medicineName} ${m.strength ?? ''}',
                          style: AppTypography.bodyLarge.copyWith(fontWeight: FontWeight.w600),
                        ),
                        Text(
                          '${m.dose ?? '1 dose'} · ${m.frequency} (${m.durationDays ?? 30} days)',
                          style: AppTypography.bodyMedium,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: () => context.go('/patient'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.accent,
              minimumSize: const Size(double.infinity, 44),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            child: const Text(
              'Done & View Dashboard',
              style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}
