import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Governance policies (spec §44) over the shared backend. A policy is checked at
/// the action's real decision point — a block policy genuinely stops a deploy.
class PoliciesRepository {
  final ApiClient _api;
  PoliciesRepository(this._api);

  Future<Map<String, dynamic>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/policies/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> toggle(int policyId, bool enabled) =>
      _api.post('policies/$policyId/toggle/', body: {'enabled': enabled});
}

final policiesRepositoryProvider = Provider<PoliciesRepository>(
  (ref) => PoliciesRepository(ref.watch(apiClientProvider)),
);

final policiesProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(policiesRepositoryProvider).list(projectId);
});
