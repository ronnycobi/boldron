import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../features/account/account_screen.dart';
import '../features/activity/activity_screen.dart';
import '../features/auth/auth_controller.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/build/build_screen.dart';
import '../features/changes/changes_screen.dart';
import '../features/projects/project_detail_screen.dart';
import '../features/projects/projects_screen.dart';
import '../features/shell/app_shell.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

int _idParam(GoRouterState state, String name) =>
    int.parse(state.pathParameters[name]!);

/// App router. Redirects based on auth state and hosts the bottom-nav shell.
/// Detail/area screens are pushed on the root navigator (full screen, over the
/// bottom nav). Deep links (spec §37) resolve against these same paths.
final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<AuthStatus>(
    ref.read(authControllerProvider).status,
  );
  ref.listen(authControllerProvider.select((s) => s.status), (_, next) {
    refresh.value = next;
  });
  ref.onDispose(refresh.dispose);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/',
    refreshListenable: refresh,
    redirect: (context, state) {
      final status = ref.read(authControllerProvider).status;
      final atAuth = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';
      if (status == AuthStatus.unauthenticated) {
        return atAuth ? null : '/login';
      }
      if (status == AuthStatus.authenticated && atAuth) {
        return '/';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/register', builder: (_, __) => const RegisterScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navShell) => AppShell(navShell: navShell),
        branches: [
          StatefulShellBranch(
            routes: [GoRoute(path: '/', builder: (_, __) => const BuildScreen())],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/projects',
                builder: (_, __) => const ProjectsScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/activity',
                builder: (_, __) => const ActivityScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/account',
                builder: (_, __) => const AccountScreen(),
              ),
            ],
          ),
        ],
      ),

      // --- full-screen project area routes (pushed over the shell) ---
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id',
        builder: (_, s) => ProjectDetailScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/changes',
        builder: (_, s) => ChangesScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/changes/:id',
        builder: (_, s) => ChangeDetailScreen(changeId: _idParam(s, 'id')),
      ),
    ],
  );
});
