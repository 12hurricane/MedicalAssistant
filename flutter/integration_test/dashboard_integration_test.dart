import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:medassist/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('End-User Browser Test: Login & Dashboard', (WidgetTester tester) async {
    app.main();
    await tester.pumpAndSettle(const Duration(seconds: 2));

    // Wait for the app to settle on the login screen
    // Tap on "Already have an account? Sign in" if we are on the register screen
    final signInLink = find.text('Already have an account? Sign in');
    if (signInLink.evaluate().isNotEmpty) {
      await tester.tap(signInLink);
      await tester.pumpAndSettle(const Duration(seconds: 1));
    }

    // Now we should be on Login Screen
    final emailField = find.byType(TextFormField).first;
    final passwordField = find.byType(TextFormField).last;
    
    await tester.enterText(emailField, 'testuser@example.com');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.enterText(passwordField, 'Password123!');
    await tester.pump(const Duration(milliseconds: 500));

    // Tap Login
    final loginButton = find.text('Sign in');
    await tester.tap(loginButton);
    await tester.pumpAndSettle(const Duration(seconds: 3));

    // We should now be on the Dashboard
    expect(find.text('Today\'s Schedule'), findsWidgets);
    
    // Check for Rx tab
    expect(find.text('Rx'), findsWidgets);

    // Give the user a moment to see it
    await Future.delayed(const Duration(seconds: 5));
  });
}
