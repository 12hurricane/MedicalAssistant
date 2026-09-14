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

/// Patient self-registration.
///
/// There is deliberately no role picker, and there is no longer anything to pick.
/// `POST /auth/register` used to accept whatever role the body carried, DOCTOR and
/// ADMIN included, so this screen's restraint was the only thing standing between an
/// anonymous form and a clinician account with a patient roster behind it — a client-side
/// guard on a server-side capability, which is to say no guard at all.
///
/// The field has since been removed from `UserRegister` rather than validated, so the
/// endpoint creates a PATIENT and cannot be asked for anything else. The absence of a
/// picker here is now a UI decision about a capability that does not exist, which is
/// what it should have been from the start.
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _confirmPassword = TextEditingController();

  bool _submitting = false;
  bool _obscure = true;
  String? _formError;
  Map<String, String> _fieldErrors = const {};
  double _strengthScore = 0.0;

  void _updateStrength(String value) {
    double score = 0.0;
    if (value.isNotEmpty) score += 0.25;
    if (value.length >= 8) score += 0.25;
    if (value.contains(RegExp(r'[A-Z]'))) score += 0.25;
    if (value.contains(RegExp(r'[0-9!@#\$%\^&\*]'))) score += 0.25;
    setState(() => _strengthScore = score);
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _phone.dispose();
    _password.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _formError = null;
      _fieldErrors = const {};
    });
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _submitting = true);
    try {
      final phone = _phone.text.trim();
      await ref.read(authControllerProvider.notifier).register(
            name: _name.text.trim(),
            email: _email.text.trim(),
            password: _password.text,
            phone: phone.isEmpty ? null : phone,
          );
    } on ValidationException catch (error) {
      setState(() {
        _fieldErrors = error.fieldErrors;
        _formError = error.fieldErrors.isEmpty ? error.message : null;
      });
      _formKey.currentState?.validate();
    } on ApiException catch (error) {
      setState(() => _formError = error.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        elevation: 0,
        scrolledUnderElevation: 0,
        shape: const Border(
          bottom: BorderSide(color: AppColors.border, width: 1.0),
        ),
        title: const Text('Create account', style: AppTypography.titleMedium),
        leading: IconButton(
          onPressed: () => context.go(AppRoutes.login),
          icon: const Icon(Icons.arrow_back, color: AppColors.textPrimary),
          tooltip: 'Back to sign in',
        ),
      ),
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
                      if (_formError != null)
                        Container(
                          margin: const EdgeInsets.only(bottom: 16),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppColors.dangerSurface,
                            borderRadius: BorderRadius.circular(4.0),
                            border: Border.all(color: AppColors.danger, width: 1.0),
                          ),
                          child: Text(
                            _formError!,
                            style: AppTypography.bodyMedium.copyWith(color: AppColors.danger),
                          ),
                        ),
                      TextFormField(
                        controller: _name,
                        decoration: InputDecoration(
                          labelText: 'Full name',
                          errorText: _fieldErrors['name'],
                        ),
                        textCapitalization: TextCapitalization.words,
                        textInputAction: TextInputAction.next,
                        enabled: !_submitting,
                        validator: (value) => (value?.trim() ?? '').isEmpty
                            ? 'Enter your name'
                            : _fieldErrors['name'],
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _email,
                        decoration: InputDecoration(
                          labelText: 'Email',
                          errorText: _fieldErrors['email'],
                        ),
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        enabled: !_submitting,
                        validator: (value) {
                          final text = value?.trim() ?? '';
                          if (text.isEmpty) return 'Enter your email address';
                          if (!text.contains('@')) return 'That does not look like an email';
                          return _fieldErrors['email'];
                        },
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _phone,
                        decoration: InputDecoration(
                          labelText: 'Mobile Phone (optional)',
                          errorText: _fieldErrors['phone'],
                        ),
                        keyboardType: TextInputType.phone,
                        textInputAction: TextInputAction.next,
                        enabled: !_submitting,
                        validator: (_) => _fieldErrors['phone'],
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _password,
                        decoration: InputDecoration(
                          labelText: 'Password',
                          errorText: _fieldErrors['password'],
                          suffixIcon: IconButton(
                            onPressed: () => setState(() => _obscure = !_obscure),
                            icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                            tooltip: _obscure ? 'Show password' : 'Hide password',
                          ),
                        ),
                        obscureText: _obscure,
                        textInputAction: TextInputAction.next,
                        enabled: !_submitting,
                        onChanged: _updateStrength,
                        validator: (value) {
                          final text = value ?? '';
                          if (text.isEmpty) return 'Choose a password';
                          if (text.length < 8) return 'Use at least 8 characters';
                          return _fieldErrors['password'];
                        },
                      ),
                      if (_password.text.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 8.0, bottom: 4.0),
                          child: Row(
                            children: [
                              Expanded(
                                child: LinearProgressIndicator(
                                  value: _strengthScore,
                                  backgroundColor: AppColors.border,
                                  color: _strengthScore < 0.5
                                      ? AppColors.danger
                                      : _strengthScore < 1.0
                                          ? AppColors.riskModerate
                                          : AppColors.riskLow,
                                  minHeight: 4,
                                ),
                              ),
                              const SizedBox(width: 8),
                              SizedBox(
                                width: 40,
                                child: Text(
                                  _strengthScore < 0.5
                                      ? 'Weak'
                                      : _strengthScore < 1.0
                                          ? 'Fair'
                                          : 'Strong',
                                  style: AppTypography.labelSmall,
                                ),
                              ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _confirmPassword,
                        decoration: const InputDecoration(
                          labelText: 'Confirm Password',
                        ),
                        obscureText: _obscure,
                        textInputAction: TextInputAction.done,
                        enabled: !_submitting,
                        onFieldSubmitted: (_) => _submitting ? null : _submit(),
                        validator: (value) {
                          if (value != _password.text) return 'Passwords do not match';
                          return null;
                        },
                      ),
                      const SizedBox(height: 24),
                      FilledButton(
                        style: FilledButton.styleFrom(
                          backgroundColor: AppColors.primary,
                          foregroundColor: AppColors.textOnPrimary,
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(4.0),
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        ),
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
                            : const Text('Create account', style: AppTypography.labelLarge),
                      ),
                      const SizedBox(height: 12),
                      TextButton(
                        style: TextButton.styleFrom(
                          foregroundColor: AppColors.primary,
                        ),
                        onPressed:
                            _submitting ? null : () => context.go(AppRoutes.login),
                        child: const Text('I already have an account'),
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
