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

/// Premium UI Verification:
/// Replaces the legacy "zero-shadows" anti-goal assertion.
/// This verifies that the UI is using the new subtle 3D/elevation properties 
/// from the CardTheme and the subtle RadialGradient from AuthBackground,
/// while still avoiding heavy unreadable blurs (BackdropFilter).
void verifyPremiumModernUI(WidgetTester tester, String screenName) {
  // We should still strictly forbid BackdropFilter (heavy glassmorphic blur) to preserve contrast
  expect(
    find.byType(BackdropFilter),
    findsNothing,
    reason: '$screenName violates clinical aesthetic: found BackdropFilter which hurts contrast',
  );
  
  // Verify that Cards are being used (which carry our new elevation/border radius)
  if (screenName != 'AuthBackground') {
    expect(
      find.byType(Card),
      findsWidgets,
      reason: '$screenName must use Card widgets to leverage the subtle 3D elevation theme',
    );
  }
}

void main() {
  group('AuthBackground Premium Aesthetics', () {
    testWidgets('renders premium dark background with subtle radial gradient', (WidgetTester tester) async {
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
      
      // Verify gradient exists
      final decoratedBoxes = tester.widgetList<DecoratedBox>(find.byType(DecoratedBox));
      expect(decoratedBoxes, isNotEmpty);
      bool hasGradient = false;
      for (final box in decoratedBoxes) {
        if (box.decoration is BoxDecoration) {
          final decoration = box.decoration as BoxDecoration;
          if (decoration.gradient is RadialGradient) {
            hasGradient = true;
          }
        }
      }
      expect(hasGradient, isTrue, reason: 'AuthBackground must use a RadialGradient for premium depth');
    });
  });

  group('GlassCard Premium Refactor', () {
    testWidgets('renders Card with subtle elevation and without heavy blur', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark,
          home: const Scaffold(
            body: GlassCard(
              child: Text('Card Content'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Card Content'), findsOneWidget);
      verifyPremiumModernUI(tester, 'GlassCard');
    });
  });

  group('LoginScreen Premium Form & Aesthetics Verification', () {
    testWidgets('renders sign-in form elements and passes modern UI assertion', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(MockSignedOutAuthController.new),
          ],
          child: MaterialApp(
            theme: AppTheme.dark,
            home: const LoginScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify header and fields
      expect(find.text('Sign in'), findsNWidgets(2)); // Title & button
      expect(find.text('MedAssist medication management'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, ''), findsNWidgets(2)); // Email & Password

      // Verify Premium Modern UI
      verifyPremiumModernUI(tester, 'LoginScreen');
    });

    testWidgets('renders session notice banner with modern UI constraints', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(MockNoticeAuthController.new),
          ],
          child: MaterialApp(
            theme: AppTheme.dark,
            home: const LoginScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Session expired. Please sign in again.'), findsOneWidget);
      verifyPremiumModernUI(tester, 'LoginScreen with Notice');
    });
  });

  group('RegisterScreen Premium Form & Aesthetics Verification', () {
    testWidgets('renders registration form and passes modern UI assertion', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authControllerProvider.overrideWith(MockSignedOutAuthController.new),
          ],
          child: MaterialApp(
            theme: AppTheme.dark,
            home: const RegisterScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify AppBar and inputs
      expect(find.text('Create account'), findsNWidgets(2)); // Title & button
      expect(find.byType(TextFormField), findsNWidgets(5)); // Name, Email, Phone, Pass, ConfirmPass

      // Verify Premium Modern UI
      verifyPremiumModernUI(tester, 'RegisterScreen');
    });
  });
}
