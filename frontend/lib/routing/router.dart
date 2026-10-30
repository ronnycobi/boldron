import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../features/account/account_screen.dart';
import '../features/activity/activity_screen.dart';
import '../features/auth/auth_controller.dart';
import '../features/auth/forgot_password_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/mfa_challenge_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/auth/welcome_screen.dart';
import '../features/account/account_security_screen.dart';
import '../features/backups/backups_screen.dart';
import '../features/comments/comments_screen.dart';
import '../features/operations/incidents_screen.dart';
import '../features/operations/operations_screen.dart';
import '../features/quality/compatibility_screen.dart';
import '../features/quality/security_screen.dart';
import '../features/quality/tests_screen.dart';
import '../features/billing/billing_screen.dart';
import '../features/build/build_screen.dart';
import '../features/changes/changes_screen.dart';
import '../features/commerce/commerce_screen.dart';
import '../features/deployments/deployment_detail_screen.dart';
import '../features/deployments/deployments_screen.dart';
import '../features/projects/environment_screen.dart';
import '../features/projects/files_screen.dart';
import '../features/projects/project_detail_screen.dart';
import '../features/projects/projects_screen.dart';
import '../features/mobile/mobile_plan_screen.dart';
import '../features/releases/releases_screen.dart';
import '../features/releases/store_listing_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/mfa_setup_screen.dart';
import '../features/settings/preferences_screen.dart';
import '../features/settings/security_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/shell/app_shell.dart';
import '../features/support/support_screen.dart';
import '../features/projects/project_ai_screen.dart';
import '../features/projects/project_repository_screen.dart';
import '../features/settings/connected_accounts_screen.dart';
import '../features/settings/data_screen.dart';
import '../features/settings/integrations_screen.dart';
import '../features/settings/notifications_screen.dart';
import '../features/team/developer_screen.dart';
import '../features/team/org_ai_screen.dart';
import '../features/team/org_audit_screen.dart';
import '../features/team/org_commerce_screen.dart';
import '../features/team/org_documents_screen.dart';
import '../features/team/org_domains_screen.dart';
import '../features/team/org_privacy_screen.dart';
import '../features/team/org_general_screen.dart';
import '../features/team/org_roles_screen.dart';
import '../features/team/team_screen.dart';
import '../features/website/analytics_screen.dart';
import '../features/website/monitoring_screen.dart';
import '../features/website/website_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

const _storeLabels = {
  'google_play': 'Google Play',
  'apple_app_store': 'Apple App Store',
  'huawei_appgallery': 'Huawei AppGallery',
};

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
      const authRoutes = {
        '/welcome',
        '/login',
        '/login/mfa',
        '/register',
        '/forgot-password'
      };
      final atAuth = authRoutes.contains(state.matchedLocation);
      if (status == AuthStatus.unauthenticated) {
        // Signed-out users land on the welcome screen first.
        return atAuth ? null : '/welcome';
      }
      if (status == AuthStatus.authenticated && atAuth) {
        return '/';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/welcome', builder: (_, __) => const WelcomeScreen()),
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(
          path: '/login/mfa', builder: (_, __) => const MfaChallengeScreen()),
      GoRoute(
          path: '/forgot-password',
          builder: (_, __) => const ForgotPasswordScreen()),
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
        path: '/deployments/:id',
        builder: (_, s) => DeploymentDetailScreen(deploymentId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/website',
        builder: (_, s) => WebsiteScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/website/monitoring',
        builder: (_, s) => MonitoringScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/website/analytics',
        builder: (_, s) => AnalyticsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/backups',
        builder: (_, s) => BackupsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/operations',
        builder: (_, s) => OperationsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/incidents',
        builder: (_, s) => IncidentsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/comments',
        builder: (_, s) => CommentsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/tests',
        builder: (_, s) => TestsScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/security',
        builder: (_, s) => ProjectSecurityScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/compatibility',
        builder: (_, s) => CompatibilityScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/commerce',
        builder: (_, s) => CommerceScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/environment',
        builder: (_, s) => EnvironmentScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/files',
        builder: (_, s) => FilesScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/ai',
        builder: (_, s) => ProjectAiScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/repository',
        builder: (_, s) => ProjectRepositoryScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/projects/:id/releases',
        builder: (_, s) => ReleasesScreen(projectId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/mobile-plan',
        builder: (_, s) =>
            MobilePlanScreen(initialBrief: s.uri.queryParameters['brief'] ?? ''),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/mobile-apps/:appId/stores/:provider/listing',
        builder: (_, s) {
          final provider = s.pathParameters['provider']!;
          return StoreListingScreen(
            appId: _idParam(s, 'appId'),
            provider: provider,
            providerLabel: _storeLabels[provider] ?? provider,
          );
        },
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
        path: '/orgs/:id/settings',
        builder: (_, s) => OrgGeneralScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/roles',
        builder: (_, s) => OrgRolesScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/ai',
        builder: (_, s) => OrgAiScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/developer',
        builder: (_, s) => DeveloperScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/audit',
        builder: (_, s) => OrgAuditScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/domains',
        builder: (_, s) => OrgDomainsScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/commerce',
        builder: (_, s) => OrgCommerceScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/orgs/:id/privacy',
        builder: (_, s) => OrgPrivacyScreen(orgId: _idParam(s, 'id')),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/integrations',
        builder: (_, __) => const IntegrationsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/notifications',
        builder: (_, __) => const NotificationsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/data',
        builder: (_, __) => const DataScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/connected',
        builder: (_, __) => const ConnectedAccountsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/documents',
        builder: (_, __) => const OrgDocumentsScreen(),
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
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/preferences',
        builder: (_, __) => const PreferencesScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/account/security',
        builder: (_, __) => const AccountSecurityScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/security',
        builder: (_, __) => const SecurityScreen(),
      ),
      GoRoute(
        parentNavigatorKey: _rootNavigatorKey,
        path: '/settings/security/mfa',
        builder: (_, __) => const MfaSetupScreen(),
      ),
    ],
  );
});
