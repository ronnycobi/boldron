import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// The Application Graph (spec §4) + Dependency Intelligence (spec §5), read-only
/// over the shared backend. The graph is composed from real project data; the
/// dependency report answers "what is affected if this part changes?".
class GraphRepository {
  final ApiClient _api;
  GraphRepository(this._api);

  Future<Map<String, dynamic>> graph(int projectId) async {
    final data = await _api.get('projects/$projectId/graph/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> dependencies(int projectId, String nodeId) async {
    final data = await _api.get('projects/$projectId/graph/?node=$nodeId');
    return (data as Map).cast<String, dynamic>();
  }
}

final graphRepositoryProvider = Provider<GraphRepository>(
  (ref) => GraphRepository(ref.watch(apiClientProvider)),
);

final graphProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(graphRepositoryProvider).graph(projectId);
});
