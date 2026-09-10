import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/providers.dart';
import '../../../../core/api/generated/api_models.dart';
import '../prescriptions_screen.dart';

/// Modal bottom sheet for adding a new prescription.
class AddPrescriptionSheet extends ConsumerStatefulWidget {
  const AddPrescriptionSheet({super.key});

  @override
  ConsumerState<AddPrescriptionSheet> createState() => _AddPrescriptionSheetState();
}

class _AddPrescriptionSheetState extends ConsumerState<AddPrescriptionSheet> {
  final _formKey = GlobalKey<FormState>();
  final _doctorController = TextEditingController();
  final _clinicController = TextEditingController();
  final _medicationNameController = TextEditingController();
  final _medicationDoseController = TextEditingController();
  
  bool _isSubmitting = false;

  @override
  void dispose() {
    _doctorController.dispose();
    _clinicController.dispose();
    _medicationNameController.dispose();
    _medicationDoseController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isSubmitting = true);

    try {
      final client = ref.read(apiClientProvider);
      
      final payload = PrescriptionCreate(
        doctorName: _doctorController.text.trim(),
        clinicName: _clinicController.text.trim(),
        prescriptionDate: DateTime.now(),
        medications: [
          PrescribedMedicationCreate(
            medicineName: _medicationNameController.text.trim(),
            dose: _medicationDoseController.text.trim(),
            frequency: '1x daily', // Defaulted for MVP
            durationDays: 30, // Defaulted for MVP
            instructions: 'Take as directed',
          ),
        ],
      );

      await client.postObject(
        ApiEndpoints.prescriptions,
        body: payload.toJson(),
        decode: PrescriptionResponse.fromJson,
      );

      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Prescription added successfully')),
        );
      }
      
      // Refresh the prescriptions list
      ref.read(prescriptionsProvider.notifier).refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error adding prescription: $e'), backgroundColor: AppColors.statusMissed),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.surface.withValues(alpha: 0.85),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.5))),
        ),
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom + 24,
          left: 24,
          right: 24,
          top: 24,
        ),
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Add Prescription', style: AppTypography.titleLarge),
              const SizedBox(height: 8),
              const Text('Enter the details of your new prescription.', style: TextStyle(color: AppColors.textSecondary)),
              const SizedBox(height: 24),
              
              TextFormField(
                controller: _doctorController,
                decoration: const InputDecoration(
                  labelText: 'Doctor Name (Optional)',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 16),
              
              TextFormField(
                controller: _clinicController,
                decoration: const InputDecoration(
                  labelText: 'Clinic Name (Optional)',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.local_hospital_outlined),
                ),
              ),
              const SizedBox(height: 24),
              
              const Text('Medication Details', style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 12),
              
              TextFormField(
                controller: _medicationNameController,
                decoration: const InputDecoration(
                  labelText: 'Medication Name',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.medication_outlined),
                ),
                validator: (val) => val == null || val.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 16),
              
              TextFormField(
                controller: _medicationDoseController,
                decoration: const InputDecoration(
                  labelText: 'Dosage (e.g. 50mg)',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.scale_outlined),
                ),
                validator: (val) => val == null || val.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 32),
              
              FilledButton(
                onPressed: _isSubmitting ? null : _submit,
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: _isSubmitting 
                    ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Text('Save Prescription', style: TextStyle(fontSize: 16)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
