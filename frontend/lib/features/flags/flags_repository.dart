import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Feature flags (spec §19) over the shared backend. A flag is off unless
/// enabled; evaluation is deterministic (rollout % + condition targeting).
class FlagsRepository {
  final ApiClient _api;
  FlagsRepository(this._api);

  Future<Map<String, dynamic>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/flags/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> toggle(int flagId, bool enabled) =>
      _api.post('flags/$flagId/toggle/', body: {'enabled': enabled});
}

final flagsRepositoryProvider = Provider<FlagsRepository>(
  (ref) => FlagsRepository(ref.watch(apiClientProvider)),
);

final flagsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(flagsRepositoryProvider).list(projectId);
});
