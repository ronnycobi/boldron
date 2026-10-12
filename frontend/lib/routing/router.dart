import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../features/account/account_screen.dart';
import '../features/activity/activity_screen.dart';
import '../features/auth/auth_controller.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/backups/backups_screen.dart';
import '../features/billing/billing_screen.dart';
import '../features/build/build_screen.dart';
import '../features/changes/changes_screen.dart';
import '../features/commerce/commerce_screen.dart';
import '../features/deployments/deployments_screen.dart';
import '../features/projects/project_detail_screen.dart';
import '../features/projects/projects_screen.dart';
import '../features/releases/releases_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/shell/app_shell.dart';
import '../features/support/support_screen.dart';
import '../features/team/team_screen.dart';
import '../features/website/website_screen.dart';

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
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/deployments',
        builder: (_, s) => DeploymentsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/website',
        builder: (_, s) => WebsiteScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/backups',
        builder: (_, s) => BackupsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/commerce',
        builder: (_, s) => CommerceScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/releases',
        builder: (_, s) => ReleasesScreen(projectId: _idParam(s, 'id')),
      ),

      // --- org-level & cross-cutting routes ---
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/billing',
        builder: (_, s) => BillingScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/team',
        builder: (_, s) => TeamScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/support',
        builder: (_, __) => const SupportScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/support/:id',
        builder: (_, s) => TicketScreen(ticketId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/search',
        builder: (_, __) => const SearchScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings',
        builder: (_, __) => const SettingsScreen(),
      ),
    ],
  );
});
