import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../app/theme/app_colors.dart';
import '../../../../app/theme/app_typography.dart';
import '../../../../core/api/api_endpoints.dart';
import '../../../../core/providers.dart';
import '../../../../core/api/generated/api_models.dart';
import '../prescriptions_screen.dart';

class _MedicationEntry {
  final nameController = TextEditingController();
  final doseController = TextEditingController();
  final durationController = TextEditingController(text: '30');
  String frequency = 'once daily';
  String instructions = 'Take as directed';

  void dispose() {
    nameController.dispose();
    doseController.dispose();
    durationController.dispose();
  }
}

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
  final List<_MedicationEntry> _medications = [];
  
  bool _isSubmitting = false;

  static const _frequencies = [
    MapEntry('once daily', 'Once daily (OD)'),
    MapEntry('twice daily', 'Twice daily (BD)'),
    MapEntry('three times daily', 'Three times daily (TID)'),
    MapEntry('four times daily', 'Four times daily (QID)'),
    MapEntry('every 8 hours', 'Every 8 hours (Q8H)'),
    MapEntry('every 12 hours', 'Every 12 hours (Q12H)'),
    MapEntry('at bedtime', 'At bedtime (HS)'),
    MapEntry('as needed', 'As needed (PRN)'),
  ];

  static const _instructionOptions = [
    'Take as directed',
    'With food',
    'Before food',
    'After food',
    'On an empty stomach',
  ];

  @override
  void initState() {
    super.initState();
    _medications.add(_MedicationEntry());
  }

  @override
  void dispose() {
    _doctorController.dispose();
    _clinicController.dispose();
    for (final med in _medications) {
      med.dispose();
    }
    super.dispose();
  }

  void _addMedication() {
    setState(() {
      _medications.add(_MedicationEntry());
    });
  }

  void _removeMedication(int index) {
    if (_medications.length <= 1) return;
    setState(() {
      final removed = _medications.removeAt(index);
      removed.dispose();
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isSubmitting = true);

    try {
      final client = ref.read(apiClientProvider);
      
      final payload = PrescriptionCreate(
        doctorName: _doctorController.text.trim().isEmpty ? null : _doctorController.text.trim(),
        clinicName: _clinicController.text.trim().isEmpty ? null : _clinicController.text.trim(),
        prescriptionDate: DateTime.now(),
        medications: _medications.map((m) {
          final days = int.tryParse(m.durationController.text.trim()) ?? 30;
          return PrescribedMedicationCreate(
            medicineName: m.nameController.text.trim(),
            dose: m.doseController.text.trim(),
            frequency: m.frequency,
            durationDays: days,
            instructions: m.instructions,
          );
        }).toList(),
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
          SnackBar(
            content: Text('Error adding prescription: $e'),
            backgroundColor: AppColors.statusMissed,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * 0.88,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        border: Border(top: BorderSide(color: AppColors.border, width: 1)),
      ),
      child: SafeArea(
        top: false,
        child: Form(
          key: _formKey,
          child: ListView(
            padding: EdgeInsets.only(
              bottom: MediaQuery.viewInsetsOf(context).bottom + 24,
              left: 20,
              right: 20,
              top: 20,
            ),
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Add Prescription', style: AppTypography.titleLarge),
                  IconButton(
                    icon: const Icon(Icons.close, color: AppColors.textSecondary),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'Enter details for the new prescription and prescribed medications.',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 20),
              
              TextFormField(
                controller: _doctorController,
                decoration: const InputDecoration(
                  labelText: 'Doctor Name (Optional)',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 12),
              
              TextFormField(
                controller: _clinicController,
                decoration: const InputDecoration(
                  labelText: 'Clinic / Hospital Name (Optional)',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.local_hospital_outlined),
                ),
              ),
              const SizedBox(height: 24),
              
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Medications (${_medications.length})',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                  ),
                  TextButton.icon(
                    onPressed: _addMedication,
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add Drug'),
                  ),
                ],
              ),
              const SizedBox(height: 8),

              for (int i = 0; i < _medications.length; i++)
                _buildMedicationCard(i),

              const SizedBox(height: 24),
              FilledButton(
                onPressed: _isSubmitting ? null : _submit,
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                child: _isSubmitting 
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('Save Prescription', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMedicationCard(int index) {
    final med = _medications[index];
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Drug #${index + 1}',
                style: const TextStyle(fontWeight: FontWeight.w600, color: AppColors.primary, fontSize: 13),
              ),
              if (_medications.length > 1)
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: AppColors.statusMissed, size: 20),
                  onPressed: () => _removeMedication(index),
                  tooltip: 'Remove',
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: med.nameController,
            decoration: const InputDecoration(
              labelText: 'Medicine Name *',
              hintText: 'e.g. Metformin, Lisinopril',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            validator: (val) => val == null || val.trim().isEmpty ? 'Required' : null,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextFormField(
                  controller: med.doseController,
                  decoration: const InputDecoration(
                    labelText: 'Dose / Strength *',
                    hintText: 'e.g. 500mg, 1 tablet',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  validator: (val) => val == null || val.trim().isEmpty ? 'Required' : null,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextFormField(
                  controller: med.durationController,
                  decoration: const InputDecoration(
                    labelText: 'Days *',
                    hintText: '30',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  keyboardType: TextInputType.number,
                  validator: (val) {
                    if (val == null || val.trim().isEmpty) return 'Required';
                    final n = int.tryParse(val.trim());
                    if (n == null || n <= 0) return 'Invalid';
                    return null;
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: med.frequency,
            decoration: const InputDecoration(
              labelText: 'Frequency',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            items: _frequencies
                .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value, style: const TextStyle(fontSize: 13))))
                .toList(),
            onChanged: (val) {
              if (val != null) setState(() => med.frequency = val);
            },
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: med.instructions,
            decoration: const InputDecoration(
              labelText: 'Instructions / Food relation',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            items: _instructionOptions
                .map((e) => DropdownMenuItem(value: e, child: Text(e, style: const TextStyle(fontSize: 13))))
                .toList(),
            onChanged: (val) {
              if (val != null) setState(() => med.instructions = val);
            },
          ),
        ],
      ),
    );
  }
}
