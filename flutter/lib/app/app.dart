import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router.dart';
import 'theme/app_theme.dart';

/// The root widget.
///
/// A [ConsumerWidget] rather than a `StatefulWidget` holding a router, so the router is
/// built by Riverpod and disposed with the container. Building a `GoRouter` in
/// `build()` would recreate it on every rebuild and reset the navigation stack.
class MedAssistApp extends ConsumerWidget {
  const MedAssistApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'MedAssist',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      routerConfig: router,
    );
  }
}
