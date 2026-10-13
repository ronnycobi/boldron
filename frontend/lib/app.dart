import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'config/app_config.dart';
import 'config/brand.dart';
import 'config/theme.dart';
import 'core/providers.dart';
import 'features/auth/auth_controller.dart';
import 'routing/router.dart';

/// Root widget. While the session is being restored (status == unknown) a splash
/// is shown; once resolved, the router takes over. Theme follows the system
/// light/dark setting (spec §35).
class BoldronApp extends ConsumerWidget {
  const BoldronApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(authControllerProvider.select((s) => s.status));

    if (status == AuthStatus.unknown) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark(),
        home: const _Splash(),
      );
    }

    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      // Dark-first, matching the website — regardless of the system setting.
      theme: AppTheme.dark(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.dark,
      routerConfig: router,
    );
  }
}

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) => Scaffold(
        body: BrandBackground(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                BrandText(
                  AppConfig.appName,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: 20),
                const CircularProgressIndicator(),
              ],
            ),
          ),
        ),
      );
}
