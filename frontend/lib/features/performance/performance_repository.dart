import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// Performance intelligence (spec §41) over the shared backend. Percentiles and
/// budget flags are computed from real recorded samples — never synthetic.
class PerformanceRepository {
  final ApiClient _api;
  PerformanceRepository(this._api);

  Future<Map<String, dynamic>> overview(int projectId) async {
    final data = await _api.get('projects/$projectId/performance/');
    return (data as Map).cast<String, dynamic>();
  }
}

final performanceRepositoryProvider = Provider<PerformanceRepository>(
  (ref) => PerformanceRepository(ref.watch(apiClientProvider)),
);

final performanceProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(performanceRepositoryProvider).overview(projectId);
});
