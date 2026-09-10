import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/providers.dart';
import '../../../core/api/api_endpoints.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/widgets/state_views.dart';
import '../dashboard/widgets/patient_background.dart';
import 'widgets/add_prescription_sheet.dart';

/// Provider that fetches the patient's prescriptions list.
final prescriptionsProvider =
    AsyncNotifierProvider<PrescriptionsNotifier, List<PrescriptionResponse>>(
        PrescriptionsNotifier.new);

class PrescriptionsNotifier extends AsyncNotifier<List<PrescriptionResponse>> {
  @override
  Future<List<PrescriptionResponse>> build() async {
    final client = ref.read(apiClientProvider);
    return client.getList(
      ApiEndpoints.prescriptions,
      decode: PrescriptionResponse.fromJson,
    );
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => build());
  }
}

/// Displays the patient's prescriptions.
class PrescriptionsScreen extends ConsumerWidget {
  const PrescriptionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prescriptions = ref.watch(prescriptionsProvider);

    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            backgroundColor: Colors.transparent,
            builder: (context) => const AddPrescriptionSheet(),
          );
        },
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add),
        label: const Text('Add Prescription', style: TextStyle(fontWeight: FontWeight.w600)),
      ),
      body: PatientBackground(
        child: RefreshIndicator(
          onRefresh: () => ref.read(prescriptionsProvider.notifier).refresh(),
          child: switch (prescriptions) {
        AsyncValue(hasValue: true, :final value?) when value.isEmpty =>
          ListView(
            children: const [
              SizedBox(height: 120),
              EmptyView(
                title: 'No prescriptions yet',
                detail:
                    'Upload a prescription image or ask your clinician to add one.',
                icon: Icons.receipt_long_outlined,
              ),
            ],
          ),
        AsyncValue(hasValue: true, :final value?) => ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 100),
            itemCount: value.length,
            itemBuilder: (context, index) {
              final rx = value[index];
              return _PrescriptionCard(prescription: rx);
            },
          ),
        AsyncValue(hasError: true, :final error?) => ListView(
            children: [
              SizedBox(
                height: MediaQuery.sizeOf(context).height * 0.5,
                child: ErrorView(
                  error: error,
                  onRetry: () =>
                      ref.read(prescriptionsProvider.notifier).refresh(),
                ),
              ),
            ],
          ),
        _ => const LoadingView(label: 'Loading prescriptions…'),
      },
        ),
      ),
    );
  }
}

class _PrescriptionCard extends StatelessWidget {
  const _PrescriptionCard({required this.prescription});

  final PrescriptionResponse prescription;

  Color _statusColor(String status) {
    switch (status.toUpperCase()) {
      case 'VERIFIED':
        return AppColors.statusTaken;
      case 'PENDING':
        return AppColors.statusPending;
      case 'REJECTED':
        return AppColors.statusMissed;
      default:
        return AppColors.textSecondary;
    }
  }

  IconData _statusIcon(String status) {
    switch (status.toUpperCase()) {
      case 'VERIFIED':
        return Icons.verified_outlined;
      case 'PENDING':
        return Icons.hourglass_empty_rounded;
      case 'REJECTED':
        return Icons.cancel_outlined;
      default:
        return Icons.help_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = prescription.verificationStatus;
    final color = _statusColor(status);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      elevation: 0,
      color: AppColors.surface,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.receipt_long_outlined,
                    size: 20, color: AppColors.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    prescription.doctorName ?? 'Prescription #${prescription.id}',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(_statusIcon(status), size: 12, color: color),
                      const SizedBox(width: 4),
                      Text(
                        status[0] + status.substring(1).toLowerCase(),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: color,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (prescription.clinicName != null) ...[
              const SizedBox(height: 6),
              Text(
                prescription.clinicName!,
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(Icons.calendar_today_outlined,
                    size: 14, color: AppColors.textDisabled),
                const SizedBox(width: 6),
                Text(
                  '${prescription.prescriptionDate.year}-'
                  '${prescription.prescriptionDate.month.toString().padLeft(2, '0')}-'
                  '${prescription.prescriptionDate.day.toString().padLeft(2, '0')}',
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textDisabled,
                  ),
                ),
                const SizedBox(width: 16),
                Icon(Icons.medication_outlined,
                    size: 14, color: AppColors.textDisabled),
                const SizedBox(width: 6),
                Text(
                  '${prescription.medications.length} medication${prescription.medications.length == 1 ? '' : 's'}',
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textDisabled,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
