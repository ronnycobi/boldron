import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/auth_controller.dart';
import '../features/auth/auth_repository.dart';
import 'api_client.dart';
import 'token_storage.dart';

/// The app's dependency graph (spec §32 layering). Everything flows one way:
/// controllers → repositories → ApiClient → TokenStorage.
///
/// Session expiry is decoupled through [sessionExpiredProvider] so the
/// ApiClient never references the AuthController (which would create a cycle):
/// the client bumps the counter, the AuthController listens and signs out.

final tokenStorageProvider =
    Provider<TokenStorage>((ref) => SecureTokenStorage());

/// Bumped by the ApiClient when a mid-session token refresh fails.
final sessionExpiredProvider = StateProvider<int>((ref) => 0);

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    tokens: ref.watch(tokenStorageProvider),
    onSessionExpired: () =>
        ref.read(sessionExpiredProvider.notifier).state++,
  );
});

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(apiClientProvider),
    ref.watch(tokenStorageProvider),
  ),
);

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  final controller = AuthController(
    ref.watch(authRepositoryProvider),
    ref.watch(tokenStorageProvider),
  );
  // When the ApiClient signals expiry, drop to the signed-out state.
  ref.listen<int>(sessionExpiredProvider, (_, __) => controller.onSessionExpired());
  return controller;
});

/// The org the user has explicitly selected in the switcher (null = not chosen).
final _selectedOrgProvider = StateProvider<int?>((ref) => null);

/// The effective active organization id: the user's explicit choice if it is
/// still one of their orgs, otherwise their first org (null if they have none).
final activeOrgProvider = Provider<int?>((ref) {
  final orgs = ref.watch(authControllerProvider.select((s) => s.user?.organizations)) ?? [];
  if (orgs.isEmpty) return null;
  final selected = ref.watch(_selectedOrgProvider);
  if (selected != null && orgs.any((o) => o.id == selected)) return selected;
  return orgs.first.id;
});

/// Call to switch the active organization.
void setActiveOrg(WidgetRef ref, int orgId) =>
    ref.read(_selectedOrgProvider.notifier).state = orgId;
