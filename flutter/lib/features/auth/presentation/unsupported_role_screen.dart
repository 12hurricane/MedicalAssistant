import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/app_colors.dart';
import '../../../app/theme/app_typography.dart';
import '../domain/session.dart';
import '../state/auth_controller.dart';

/// A dead end for an account this app cannot serve.
///
/// One way to arrive now: the backend reported a role string this build has never
/// heard of, so [AppRole.fromWire] returned [AppRole.unknown] and the router refused
/// to guess. That is a real case rather than a defensive one — the client is deployed
/// separately from the API, so a newer backend can name a role an older app predates.
///
/// This screen previously had a second arm for CAREGIVER, whose flow was never built.
/// That role no longer exists (backend migration `9f2c1d7ab4e0`), so the screen is
/// kept and the arm is gone. The alternative to a screen like this is dropping an
/// unrecognised account onto the patient dashboard, where it would see an empty
/// schedule and reasonably conclude its data had been lost.
class UnsupportedRoleScreen extends ConsumerWidget {
  const UnsupportedRoleScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(currentSessionProvider);

    // The raw wire value, not the parsed enum: the parsed value is `unknown` by
    // definition here, so echoing it would tell the reader nothing. What the server
    // actually said is the one piece of information worth putting on screen, and it is
    // what makes a support request or a bug report actionable.
    final reported = session?.user.role ?? 'unknown';

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.no_accounts_outlined,
                    size: 48,
                    color: AppColors.textDisabled,
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'This account type is not supported',
                    textAlign: TextAlign.center,
                    style: AppTypography.titleLarge,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'The server reported the role "$reported", which this version of '
                    'the app does not recognise. Updating the app may help.',
                    textAlign: TextAlign.center,
                    style: AppTypography.bodyMedium,
                  ),
                  const SizedBox(height: 28),
                  OutlinedButton.icon(
                    onPressed: () =>
                        ref.read(authControllerProvider.notifier).logout(),
                    icon: const Icon(Icons.logout),
                    label: const Text('Sign out'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
