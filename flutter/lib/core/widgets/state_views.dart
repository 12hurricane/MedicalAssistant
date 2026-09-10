import 'package:flutter/material.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_typography.dart';
import '../api/api_exception.dart';

/// A centred spinner with a label.
///
/// Labelled because an unexplained spinner on a medication screen is indistinguishable
/// from a hang, and the difference matters when someone is waiting to record a dose.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.label});

  final String? label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const CircularProgressIndicator(),
          if (label != null) ...[
            const SizedBox(height: 16),
            Text(label!, style: AppTypography.bodyMedium),
          ],
        ],
      ),
    );
  }
}

/// A failure, with a retry when retrying could plausibly help.
///
/// [ContractException] is called out separately: it means the app and the backend
/// disagree about the schema, so "Try again" is a lie — the fix is a rebuild. Showing
/// a retry button there trains people to mash it.
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  bool get _retryable => error is! ContractException && error is! ForbiddenException;

  @override
  Widget build(BuildContext context) {
    final message = error is ApiException
        ? (error as ApiException).message
        : 'Something went wrong.';

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 40, color: AppColors.statusMissed),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: AppTypography.bodyLarge,
            ),
            if (error is ContractException) ...[
              const SizedBox(height: 8),
              Text(
                'This version of the app does not match the server. '
                'Update the app rather than retrying.',
                textAlign: TextAlign.center,
                style: AppTypography.bodyMedium,
              ),
            ],
            if (onRetry != null && _retryable) ...[
              const SizedBox(height: 20),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Try again'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Nothing to show, said plainly.
class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.title,
    this.detail,
    this.icon = Icons.inbox_outlined,
  });

  final String title;
  final String? detail;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 40, color: AppColors.textDisabled),
            const SizedBox(height: 12),
            Text(title, textAlign: TextAlign.center, style: AppTypography.titleMedium),
            if (detail != null) ...[
              const SizedBox(height: 6),
              Text(detail!, textAlign: TextAlign.center, style: AppTypography.bodyMedium),
            ],
          ],
        ),
      ),
    );
  }
}
