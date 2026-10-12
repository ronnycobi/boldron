import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';
import 'project_models.dart';

class ProjectsRepository {
  final ApiClient _api;
  ProjectsRepository(this._api);

  Future<List<Project>> list() async {
    final data = await _api.get('projects/');
    return (data as List)
        .map((p) => Project.fromJson(p as Map<String, dynamic>))
        .toList();
  }

  Future<Project> get(int id) async {
    final data = await _api.get('projects/$id/');
    return Project.fromJson(data as Map<String, dynamic>);
  }

  /// Start a build from a plain-language brief. Returns the new project id.
  Future<int> build(String brief, {int? organization}) async {
    final data = await _api.post('build/', body: {
      'brief': brief,
      if (organization != null) 'organization': organization,
    });
    return (data as Map)['project']['id'] as int;
  }

  Future<BuildStatus> buildStatus(int projectId) async {
    final data = await _api.get('projects/$projectId/build-status/');
    return BuildStatus.fromJson(data as Map<String, dynamic>);
  }
}

final projectsRepositoryProvider = Provider<ProjectsRepository>(
  (ref) => ProjectsRepository(ref.watch(apiClientProvider)),
);

/// The signed-in user's projects. `ref.invalidate(projectsProvider)` refreshes.
final projectsProvider = FutureProvider<List<Project>>(
  (ref) => ref.watch(projectsRepositoryProvider).list(),
);

/// One project by id (used by the detail hub; supports deep links).
final projectProvider = FutureProvider.family<Project, int>(
  (ref, id) => ref.watch(projectsRepositoryProvider).get(id),
);

/// Live build status for one project. The detail screen re-reads this on a
/// timer while the build is running (the provider itself stays simple).
final buildStatusProvider = FutureProvider.family<BuildStatus, int>(
  (ref, projectId) =>
      ref.watch(projectsRepositoryProvider).buildStatus(projectId),
);
