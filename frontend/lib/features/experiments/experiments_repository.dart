import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// A/B experiments (spec §20) over the shared backend. Results are real counts;
/// a winner is only reported when the data is statistically significant.
class ExperimentsRepository {
  final ApiClient _api;
  ExperimentsRepository(this._api);

  Future<Map<String, dynamic>> list(int projectId) async {
    final data = await _api.get('projects/$projectId/experiments/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setStatus(int id, String status) =>
      _api.post('experiments/$id/status/', body: {'status': status});
}

final experimentsRepositoryProvider = Provider<ExperimentsRepository>(
  (ref) => ExperimentsRepository(ref.watch(apiClientProvider)),
);

final experimentsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(experimentsRepositoryProvider).list(projectId);
});
