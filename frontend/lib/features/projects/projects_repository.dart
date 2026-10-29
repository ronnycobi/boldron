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

  /// A project's environment variables for one environment (secret values come
  /// back masked). Returns {environments: [...], variables: [...]}.
  Future<Map<String, dynamic>> envVars(int projectId,
      {String environment = 'development'}) async {
    final data = await _api.get('projects/$projectId/env/',
        query: {'environment': environment});
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setEnvVar(int projectId, String key, String value,
          {bool isSecret = false, String environment = 'development'}) =>
      _api.post('projects/$projectId/env/', body: {
        'key': key,
        'value': value,
        'is_secret': isSecret,
        'environment': environment,
      });

  Future<void> deleteEnvVar(int projectId, int varId) =>
      _api.delete('projects/$projectId/env/$varId/');

  Future<Map<String, dynamic>> projectAi(int projectId) async {
    final data = await _api.get('projects/$projectId/ai/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> setProjectAi(int projectId,
          {String provider = '', String model = ''}) =>
      _api.patch('projects/$projectId/ai/',
          body: {'preferred_provider': provider, 'preferred_model': model});

  Future<Map<String, dynamic>> projectRepository(int projectId) async {
    final data = await _api.get('projects/$projectId/repository/');
    return (data as Map).cast<String, dynamic>();
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

/// A project's environment variables for one environment.
final envVarsProvider = FutureProvider.family<Map<String, dynamic>,
    ({int projectId, String environment})>(
  (ref, args) => ref
      .watch(projectsRepositoryProvider)
      .envVars(args.projectId, environment: args.environment),
);

/// A project's AI preference (own + effective + options).
final projectAiProvider =
    FutureProvider.family<Map<String, dynamic>, int>(
  (ref, projectId) => ref.watch(projectsRepositoryProvider).projectAi(projectId),
);

/// A project's local git repository status.
final projectRepositoryStatusProvider =
    FutureProvider.family<Map<String, dynamic>, int>(
  (ref, projectId) =>
      ref.watch(projectsRepositoryProvider).projectRepository(projectId),
);
