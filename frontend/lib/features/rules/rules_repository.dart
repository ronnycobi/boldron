import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Business rules (spec §12-13) over the shared backend. Honest: a rule is shown
/// as "enforced" only when it carries a definition the engine can evaluate;
/// otherwise it is documented policy. Evaluation is a real deterministic run.
class RulesRepository {
  final ApiClient _api;
  RulesRepository(this._api);

  Future<Map<String, dynamic>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/rules/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> importFromContext(int projectId) async {
    final data = await _api.post('projects/$projectId/rules/import/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setStatus(int ruleId, String status) =>
      _api.post('rules/$ruleId/status/', body: {'status': status});

  Future<Map<String, dynamic>> evaluate(
      int projectId, Map<String, dynamic> facts) async {
    final data = await _api.post('projects/$projectId/rules/evaluate/',
        body: {'facts': facts});
    return (data as Map).cast<String, dynamic>();
  }
}

final rulesRepositoryProvider = Provider<RulesRepository>(
  (ref) => RulesRepository(ref.watch(apiClientProvider)),
);

final rulesProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(rulesRepositoryProvider).list(projectId);
});
