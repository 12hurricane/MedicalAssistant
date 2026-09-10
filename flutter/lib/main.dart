import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';

/// Entry point.
///
/// Nothing is initialised here beyond the Riverpod container. Session restore is the
/// auth controller's job and happens while the splash route is on screen, so the first
/// frame is not blocked on a network call — a backend that is slow or down still gets to
/// a usable login screen.
void main() {
  runApp(const ProviderScope(child: MedAssistApp()));
}
