import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// The platform's quality surfaces for a project — all read-only over the shared
/// backend ledgers/analysis (tests, security, compatibility). No business logic here.
class QualityRepository {
  final ApiClient _api;
  QualityRepository(this._api);

  // --- Tests ---
  Future<Map<String, dynamic>> tests(int projectId) async {
    final data = await _api.get('projects/$projectId/tests/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> runTests(int projectId) =>
      _api.post('projects/$projectId/tests/');

  Future<void> proposeFix(int projectId, int runId) =>
      _api.post('projects/$projectId/tests/$runId/fix/');

  // --- Security ---
  Future<Map<String, dynamic>> security(int projectId) async {
    final data = await _api.get('projects/$projectId/security/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> runScan(int projectId) =>
      _api.post('projects/$projectId/security/');

  // --- Compatibility ---
  Future<Map<String, dynamic>> compatibility(int projectId) async {
    final data = await _api.get('projects/$projectId/compatibility/');
    return (data as Map).cast<String, dynamic>();
  }
}

final qualityRepositoryProvider = Provider<QualityRepository>(
  (ref) => QualityRepository(ref.watch(apiClientProvider)),
);

final testsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(qualityRepositoryProvider).tests(projectId);
});

final securityProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(qualityRepositoryProvider).security(projectId);
});

final compatibilityProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(qualityRepositoryProvider).compatibility(projectId);
});
