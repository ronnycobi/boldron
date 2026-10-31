import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Project Health Score (spec §30) over the shared backend. Read-only and
/// composed from the project's real ledgers; a project with no signal scores
/// unknown, never a fabricated 100.
class HealthRepository {
  final ApiClient _api;
  HealthRepository(this._api);

  Future<Map<String, dynamic>> health(int projectId) async {
    final data = await _api.get('projects/$projectId/health/');
    return (data as Map).cast<String, dynamic>();
  }
}

final healthRepositoryProvider = Provider<HealthRepository>(
  (ref) => HealthRepository(ref.watch(apiClientProvider)),
);

final healthProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(healthRepositoryProvider).health(projectId);
});
