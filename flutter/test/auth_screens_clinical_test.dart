import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medassist/app/theme/app_theme.dart';
import 'package:medassist/features/auth/presentation/auth_background.dart';
import 'package:medassist/features/auth/presentation/login_screen.dart';
import 'package:medassist/features/auth/presentation/register_screen.dart';
import 'package:medassist/features/auth/state/auth_controller.dart';
import 'package:medassist/widgets/glass_card.dart';

class MockSignedOutAuthController extends AuthController {
  @override
  AuthState build() => const AuthSignedOut();
}

class MockNoticeAuthController extends AuthController {
  @override
  AuthState build() => const AuthSignedOut(notice: 'Session expired. Please sign in again.');
}

/// Reflective Anti-Goal Assertion:
/// Iterates through all DecoratedBox widgets in the render tree and mathematically
/// asserts that boxShadow and gradient are strictly null.
void verifyZeroShadowsAndGradients(WidgetTester tester, String screenName) {
  final decoratedBoxes = tester.widgetList<DecoratedBox>(find.byType(DecoratedBox));
  expect(decoratedBoxes, isNotEmpty, reason: '$screenName must contain DecoratedBox widgets');

  for (final box in decoratedBoxes) {
    final decoration = box.decoration;
    if (decoration is BoxDecoration) {
      expect(
        decoration.boxShadow,
        isNull,
        reason: '$screenName violates clinical aesthetic: found BoxShadow in $decoration',
      );
      expect(
        decoration.gradient,
        isNull,
        reason: '$screenName violates clinical aesthetic: found Gradient in $decoration',
      );
    }
  }

  // Strictly forbid BackdropFilter (glassmorphic blur)
  expect(
    find.byType(BackdropFilter),
    findsNothing,
    reason: '$screenName violates clinical aesthetic: found BackdropFilter',
  );
}

void main() {
  group('AuthBackground Clinical Aesthetics', () {
    testWidgets('renders flat background without gradients or ambient blobs', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: AuthBackground(
              child: Text('Clinical Content'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Clinical Content'), findsOneWidget);
      verifyZeroShadowsAndGradients(tester, 'AuthBackground');
    });
  });

  group('GlassCard Clinical Refactor', () {
    testWidgets('renders flat surface with solid border and zero shadows or blur', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: GlassCard(
              child: Text('Card Content'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Card Content'), findsOneWidget);
      verifyZeroShadowsAndGradients(tester, 'GlassCard');
    });
  });

  group('LoginScreen Clinical Form & Anti-Goal Verification', () {
    testWidgets('renders sign-in form elements and passes zero-shadows assertion', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(MockSignedOutAuthController.new),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: const LoginScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify header and fields
      expect(find.text('Sign in'), findsNWidgets(2)); // Title & button
      expect(find.text('MedAssist medication management'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, ''), findsNWidgets(2)); // Email & Password

      // Verify Reflective Anti-Goal Assertions
      verifyZeroShadowsAndGradients(tester, 'LoginScreen');
    });

    testWidgets('renders flat session notice banner with zero shadows', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(MockNoticeAuthController.new),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: const LoginScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Session expired. Please sign in again.'), findsOneWidget);
      verifyZeroShadowsAndGradients(tester, 'LoginScreen with Notice');
    });
  });

  group('RegisterScreen Clinical Form & Anti-Goal Verification', () {
    testWidgets('renders registration form and passes zero-shadows assertion', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(MockSignedOutAuthController.new),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: const RegisterScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify AppBar and inputs
      expect(find.text('Create account'), findsNWidgets(2)); // Title & button
      expect(find.byType(TextFormField), findsNWidgets(5)); // Name, Email, Phone, Pass, ConfirmPass

      // Verify Reflective Anti-Goal Assertions
      verifyZeroShadowsAndGradients(tester, 'RegisterScreen');
    });
  });
}
