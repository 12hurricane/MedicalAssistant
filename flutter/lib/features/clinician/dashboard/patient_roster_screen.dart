import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/api/api_endpoints.dart';
import '../../../core/api/api_exception.dart';
import '../../../core/api/generated/api_models.dart';
import '../../../core/providers.dart';
import '../../../core/widgets/state_views.dart';
import '../../auth/state/auth_controller.dart';

/// Provider for clinician's patient roster.
final patientRosterProvider =
    AsyncNotifierProvider<PatientRosterNotifier, List<PatientResponse>>(
        PatientRosterNotifier.new);

class PatientRosterNotifier extends AsyncNotifier<List<PatientResponse>> {
  String? _searchQuery;

  @override
  Future<List<PatientResponse>> build() async {
    final client = ref.read(apiClientProvider);
    final endpoint = _searchQuery != null && _searchQuery!.trim().isNotEmpty
        ? '${ApiEndpoints.patients}?search=${Uri.encodeComponent(_searchQuery!.trim())}'
        : ApiEndpoints.patients;

    return client.getList(
      endpoint,
      decode: PatientResponse.fromJson,
    );
  }

  void search(String query) {
    _searchQuery = query;
    ref.invalidateSelf();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(() => build());
  }
}

/// Clinician portal patient roster screen.
class PatientRosterScreen extends ConsumerStatefulWidget {
  const PatientRosterScreen({super.key});

  @override
  ConsumerState<PatientRosterScreen> createState() => _PatientRosterScreenState();
}

class _PatientRosterScreenState extends ConsumerState<PatientRosterScreen> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final rosterAsync = ref.watch(patientRosterProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        elevation: 0,
        shape: const Border(bottom: BorderSide(color: AppColors.border, width: 1)),
        title: Row(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: const BoxDecoration(
                color: AppColors.primary,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              'Clinician Portal — Patient Roster',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: AppColors.textSecondary),
            tooltip: 'Refresh roster',
            onPressed: () => ref.read(patientRosterProvider.notifier).refresh(),
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: AppColors.textSecondary),
            tooltip: 'Sign out',
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 800),
          child: Column(
            children: [
              // Search & Filter bar
              Container(
                padding: const EdgeInsets.all(16),
                decoration: const BoxDecoration(
                  color: AppColors.surface,
                  border: Border(bottom: BorderSide(color: AppColors.border, width: 1)),
                ),
                child: TextField(
                  controller: _searchController,
                  decoration: InputDecoration(
                    hintText: 'Search patients by name or email...',
                    prefixIcon: const Icon(Icons.search, color: AppColors.textSecondary),
                    suffixIcon: _searchController.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 18),
                            onPressed: () {
                              _searchController.clear();
                              ref.read(patientRosterProvider.notifier).search('');
                            },
                          )
                        : null,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: const BorderSide(color: AppColors.border),
                    ),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  ),
                  onChanged: (val) {
                    ref.read(patientRosterProvider.notifier).search(val);
                  },
                ),
              ),

              // Roster list
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () => ref.read(patientRosterProvider.notifier).refresh(),
                  child: switch (rosterAsync) {
                    AsyncValue(hasValue: true, :final value?) when value.isEmpty =>
                      ListView(
                        children: const [
                          SizedBox(height: 100),
                          EmptyView(
                            title: 'No patients found',
                            detail: 'No registered patients match the current query.',
                            icon: Icons.people_outline,
                          ),
                        ],
                      ),
                    AsyncValue(hasValue: true, :final value?) => ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: value.length,
                        itemBuilder: (context, index) {
                          final patient = value[index];
                          return _PatientCard(patient: patient);
                        },
                      ),
                    AsyncValue(hasError: true, :final error?)
                        when error is ForbiddenException =>
                      ListView(
                        children: const [
                          SizedBox(height: 100),
                          _AccessDeniedView(),
                        ],
                      ),
                    AsyncValue(hasError: true, :final error?) => ErrorView(
                        error: error,
                        onRetry: () => ref.read(patientRosterProvider.notifier).refresh(),
                      ),
                    _ => const LoadingView(label: 'Loading patient roster...'),
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PatientCard extends StatelessWidget {
  const _PatientCard({required this.patient});

  final PatientResponse patient;

  @override
  Widget build(BuildContext context) {
    final displayName = patient.name ?? 'Patient #${patient.id}';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 20,
                  backgroundColor: AppColors.surfaceVariant,
                  child: Text(
                    displayName.isNotEmpty ? displayName[0].toUpperCase() : 'P',
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      color: AppColors.primary,
                      fontSize: 16,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              displayName,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                                color: AppColors.textPrimary,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceVariant,
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Text(
                              'ID: ${patient.id}',
                              style: const TextStyle(
                                fontFamily: 'JetBrains Mono',
                                fontSize: 11,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (patient.email != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          patient.email!,
                          style: const TextStyle(
                            fontSize: 13,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                IntrinsicWidth(
                  child: FilledButton.tonal(
                    onPressed: () {
                      context.go('/clinician/patient/${patient.id}');
                    },
                    style: FilledButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('Review', style: TextStyle(fontSize: 13)),
                        SizedBox(width: 4),
                        Icon(Icons.chevron_right, size: 16),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Divider(color: AppColors.border, height: 1),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.schedule, size: 13, color: AppColors.textDisabled),
                    const SizedBox(width: 4),
                    Text(
                      patient.timezone,
                      style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                    ),
                  ],
                ),
                if (patient.gender != null) ...[
                  Text('•', style: TextStyle(color: AppColors.textDisabled)),
                  Text(
                    patient.gender!,
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                  ),
                ],
                if (patient.bloodGroup != null) ...[
                  Text('•', style: TextStyle(color: AppColors.textDisabled)),
                  Text(
                    'Blood: ${patient.bloodGroup}',
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                  ),
                ],
                if (patient.allergies.isNotEmpty) ...[
                  Text('•', style: TextStyle(color: AppColors.textDisabled)),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.statusMissed.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: AppColors.statusMissed.withValues(alpha: 0.3)),
                    ),
                    child: Text(
                      'Allergies: ${patient.allergies.join(", ")}',
                      style: const TextStyle(fontSize: 11, color: AppColors.statusMissed, fontWeight: FontWeight.w500),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Controlled display for a 403 response on the roster endpoint.
///
/// The backend is the authorization authority. A 403 here means the
/// authenticated user is not permitted to view any patient roster —
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
              'You do not have permission to view the patient roster. '
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
