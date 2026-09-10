import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/router.dart';
import '../../../app/theme/app_colors.dart';
import '../../../app/theme/app_typography.dart';
import '../../../core/api/api_exception.dart';
import '../../../widgets/glass_card.dart';
import '../state/auth_controller.dart';
import 'auth_background.dart';

/// Sign-in against the live backend.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();

  bool _submitting = false;
  bool _obscure = true;
  String? _formError;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _formError = null);
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _submitting = true);
    try {
      await ref.read(authControllerProvider.notifier).login(
            email: _email.text.trim(),
            password: _password.text,
          );
      // No navigation here. The router redirects on the auth state change, so there is
      // one place that decides where a signed-in user belongs.
    } on ValidationException catch (error) {
      // 422 from the form-encoded login: a missing or malformed field.
      setState(() => _formError = error.fieldErrors.values.join('\n'));
    } on ApiException catch (error) {
      setState(() => _formError = error.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // A notice from the auth layer — an expired session, or a restore that could not
    // reach the backend. Distinct from _formError, which is about this attempt.
    final authState = ref.watch(authControllerProvider);
    final notice = authState is AuthSignedOut ? authState.notice : null;

    return Scaffold(
      body: AuthBackground(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: GlassCard(
                child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(
                      Icons.medication_outlined,
                      size: 48,
                      color: AppColors.primary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Sign in',
                      textAlign: TextAlign.center,
                      style: AppTypography.headlineMedium,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'MedAssist medication management',
                      textAlign: TextAlign.center,
                      style: AppTypography.bodyMedium,
                    ),
                    const SizedBox(height: 28),
                    if (notice != null) _Banner(notice, tone: _BannerTone.notice),
                    if (_formError != null) _Banner(_formError!, tone: _BannerTone.error),
                    TextFormField(
                      controller: _email,
                      decoration: const InputDecoration(labelText: 'Email'),
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      enabled: !_submitting,
                      validator: (value) {
                        final text = value?.trim() ?? '';
                        if (text.isEmpty) return 'Enter your email address';
                        // Deliberately loose. The backend is the authority on what it
                        // accepts; a strict client regex would reject valid addresses.
                        if (!text.contains('@')) return 'That does not look like an email';
                        return null;
                      },
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: _password,
                      decoration: InputDecoration(
                        labelText: 'Password',
                        suffixIcon: IconButton(
                          onPressed: () => setState(() => _obscure = !_obscure),
                          icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                          tooltip: _obscure ? 'Show password' : 'Hide password',
                        ),
                      ),
                      obscureText: _obscure,
                      autofillHints: const [AutofillHints.password],
                      textInputAction: TextInputAction.done,
                      enabled: !_submitting,
                      onFieldSubmitted: (_) => _submitting ? null : _submit(),
                      validator: (value) =>
                          (value ?? '').isEmpty ? 'Enter your password' : null,
                    ),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton(
                        onPressed: _submitting ? null : () {}, // Placeholder
                        child: const Text('Forgot password?'),
                      ),
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: _submitting ? null : _submit,
                      child: _submitting
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2.5,
                                color: AppColors.textOnPrimary,
                              ),
                            )
                          : const Text('Sign in'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: _submitting
                          ? null
                          : () => context.go(AppRoutes.register),
                      child: const Text('Create an account'),
                    ),
                  ],
                ),
              ),
            ),
              ),
          ),
        ),
      ),
    );
  }
}

enum _BannerTone { notice, error }

class _Banner extends StatelessWidget {
  const _Banner(this.message, {required this.tone});

  final String message;
  final _BannerTone tone;

  @override
  Widget build(BuildContext context) {
    final isError = tone == _BannerTone.error;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isError ? const Color(0xFFFDECEC) : AppColors.primaryLight,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isError ? AppColors.statusMissed : AppColors.primary,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            isError ? Icons.error_outline : Icons.info_outline,
            size: 20,
            color: isError ? AppColors.statusMissed : AppColors.primaryDark,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: AppTypography.bodyMedium.copyWith(color: AppColors.textPrimary),
            ),
          ),
        ],
      ),
    );
  }
}
