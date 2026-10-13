import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/router.dart';
import '../../../app/theme/app_colors.dart';
import '../../auth/state/auth_controller.dart';
import '../adherence/adherence_analytics_screen.dart';
import '../prescriptions/prescriptions_screen.dart';
import '../profile/profile_screen.dart';
import 'patient_dashboard_screen.dart';

/// Shell widget that provides bottom navigation for the patient portal.
class PatientShellScreen extends ConsumerStatefulWidget {
  const PatientShellScreen({super.key});

  @override
  ConsumerState<PatientShellScreen> createState() => _PatientShellScreenState();
}

class _PatientShellScreenState extends ConsumerState<PatientShellScreen> {
  int _currentIndex = 0;

  static const _titles = ['Today\'s Doses', 'Prescriptions', 'Adherence Analytics', 'Profile'];

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(currentSessionProvider);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _titles[_currentIndex],
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
                fontSize: 18,
              ),
            ),
            if (_currentIndex == 0 && session != null)
              Text(
                'Hello, ${_firstName(session.displayName)}',
                style: const TextStyle(
                  fontWeight: FontWeight.w500,
                  color: AppColors.textSecondary,
                  fontSize: 12,
                ),
              ),
          ],
        ),
        backgroundColor: AppColors.surface,
        elevation: 0,
        shape: const Border(bottom: BorderSide(color: AppColors.border, width: 1)),
        actions: [
          if (_currentIndex != 3) // Profile tab has its own sign-out
            IconButton(
              onPressed: () =>
                  ref.read(authControllerProvider.notifier).logout(),
              icon: const Icon(Icons.logout_rounded,
                  color: AppColors.textSecondary),
              tooltip: 'Sign out',
            ),
        ],
      ),
      body: Container(
        color: AppColors.background,
        child: IndexedStack(
          index: _currentIndex,
          children: const [
            _DashboardContent(),
            PrescriptionsScreen(),
            AdherenceAnalyticsScreen(),
            ProfileScreen(),
          ],
        ),
      ),
      floatingActionButton: _currentIndex == 0 // Only show on dashboard
          ? FloatingActionButton(
              onPressed: () => context.go(AppRoutes.patientAgentChat),
              backgroundColor: AppColors.primary,
              tooltip: 'Chat with MedAssist AI',
              child: const Icon(Icons.smart_toy_rounded, color: Colors.white),
            )
          : _currentIndex == 1 // Prescriptions
              ? FloatingActionButton.extended(
                  onPressed: () => context.go(AppRoutes.patientUpload),
                  backgroundColor: AppColors.primary,
                  icon: const Icon(Icons.document_scanner, color: Colors.white),
                  label: const Text('Upload Rx', style: TextStyle(color: Colors.white)),
                )
              : null,
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: AppColors.surface,
          border: Border(top: BorderSide(color: AppColors.border, width: 1)),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _NavItem(
                  icon: Icons.calendar_today_rounded,
                  label: 'Today',
                  isActive: _currentIndex == 0,
                  onTap: () => setState(() => _currentIndex = 0),
                ),
                _NavItem(
                  icon: Icons.receipt_long_rounded,
                  label: 'Rx',
                  isActive: _currentIndex == 1,
                  onTap: () => setState(() => _currentIndex = 1),
                ),
                _NavItem(
                  icon: Icons.insights_rounded,
                  label: 'Analytics',
                  isActive: _currentIndex == 2,
                  onTap: () => setState(() => _currentIndex = 2),
                ),
                _NavItem(
                  icon: Icons.person_rounded,
                  label: 'Profile',
                  isActive: _currentIndex == 3,
                  onTap: () => setState(() => _currentIndex = 3),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String _firstName(String full) {
    final trimmed = full.trim();
    if (trimmed.isEmpty) return 'there';
    return trimmed.split(RegExp(r'\s+')).first;
  }
}

class _DashboardContent extends ConsumerWidget {
  const _DashboardContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return const SafeArea(child: PatientDashboardBody());
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.isActive,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool isActive;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: isActive
              ? AppColors.primary.withValues(alpha: 0.1)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 20,
              color: isActive ? AppColors.primary : AppColors.textDisabled,
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
                color: isActive ? AppColors.primary : AppColors.textDisabled,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
