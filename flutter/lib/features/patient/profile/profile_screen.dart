import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/app_colors.dart';
import '../../../app/theme/app_typography.dart';
import '../../auth/state/auth_controller.dart';
import '../dashboard/widgets/patient_background.dart';

/// The patient's profile/settings screen.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(currentSessionProvider);

    return PatientBackground(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 100),
        children: [
        // Avatar + Name
        Center(
          child: Column(
            children: [
              CircleAvatar(
                radius: 44,
                backgroundColor: AppColors.primaryLight,
                child: Text(
                  _initials(session?.displayName ?? '?'),
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: AppColors.primary,
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                session?.displayName ?? 'Patient',
                style: AppTypography.titleLarge,
              ),
              const SizedBox(height: 4),
              Text(
                session?.user.email ?? '',
                style: AppTypography.bodyMedium.copyWith(
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  session?.user.role ?? 'patient',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.accent,
                  ),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 32),

        // Settings tiles
        _SettingsTile(
          icon: Icons.notifications_outlined,
          title: 'Notifications',
          subtitle: 'Dose reminders & alerts',
          onTap: () {},
        ),
        _SettingsTile(
          icon: Icons.schedule_outlined,
          title: 'Timezone',
          subtitle: 'UTC',
          onTap: () {},
        ),
        _SettingsTile(
          icon: Icons.security_outlined,
          title: 'Privacy & Security',
          subtitle: 'Account protection settings',
          onTap: () {},
        ),
        _SettingsTile(
          icon: Icons.help_outline,
          title: 'Help & Support',
          subtitle: 'FAQ, contact, report a bug',
          onTap: () {},
        ),

        const SizedBox(height: 24),

        // Sign Out
        OutlinedButton.icon(
          onPressed: () =>
              ref.read(authControllerProvider.notifier).logout(),
          icon: const Icon(Icons.logout_rounded, size: 18),
          label: const Text('Sign Out'),
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.danger,
            side: BorderSide(color: AppColors.danger.withValues(alpha: 0.3)),
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ],
    ));
  }

  static String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return ''.toUpperCase();
  }
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.5)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
          child: ListTile(
            leading: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppColors.primaryLight,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: AppColors.primary, size: 20),
            ),
            title: Text(
              title,
              style: const TextStyle(fontWeight: FontWeight.w600, color: AppColors.textPrimary),
            ),
            subtitle: Text(
              subtitle,
              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
            trailing: const Icon(Icons.chevron_right_rounded, color: AppColors.textDisabled),
            onTap: onTap,
          ),
        ),
      ),
    );
  }
}
