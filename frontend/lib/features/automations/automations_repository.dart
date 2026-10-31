import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Automations (spec §10-11) over the shared backend. An automation reacts to a
/// real event, checks conditions and runs actions; every run records each
/// action's honest outcome (done / skipped / failed) — nothing is faked.
class AutomationsRepository {
  final ApiClient _api;
  AutomationsRepository(this._api);

  Future<Map<String, dynamic>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/automations/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setStatus(int id, String status) =>
      _api.post('automations/$id/status/', body: {'status': status});

  Future<Map<String, dynamic>> testRun(
      int id, Map<String, dynamic> facts) async {
    final data = await _api.post('automations/$id/run/', body: {'facts': facts});
    return (data as Map).cast<String, dynamic>();
  }
}

final automationsRepositoryProvider = Provider<AutomationsRepository>(
  (ref) => AutomationsRepository(ref.watch(apiClientProvider)),
);

final automationsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(automationsRepositoryProvider).list(projectId);
});
