import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class Deployment {
  final int id;
  final String environment;
  final String provider;
  final String status;
  final String url;
  final String createdAt;

  const Deployment({
    required this.id,
    required this.environment,
    required this.provider,
    required this.status,
    required this.url,
    required this.createdAt,
  });

  factory Deployment.fromJson(Map<String, dynamic> j) => Deployment(
        id: j['id'] as int,
        environment: (j['environment'] ?? '') as String,
        provider: (j['provider'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        url: (j['url'] ?? '') as String,
        createdAt: (j['created_at'] ?? '') as String,
      );
}

class EnvironmentSummary {
  final String environment;
  final String label;
  final Deployment? latest;

  const EnvironmentSummary({
    required this.environment,
    required this.label,
    required this.latest,
  });

  factory EnvironmentSummary.fromJson(Map<String, dynamic> j) =>
      EnvironmentSummary(
        environment: (j['environment'] ?? '') as String,
        label: (j['label'] ?? '') as String,
        latest: j['latest'] == null
            ? null
            : Deployment.fromJson(j['latest'] as Map<String, dynamic>),
      );
}

class DeploymentsRepository {
  final ApiClient _api;
  DeploymentsRepository(this._api);

  Future<List<EnvironmentSummary>> environments(int projectId) async {
    final data = await _api.get('projects/$projectId/environments/');
    return ((data as Map)['environments'] as List)
        .map((e) => EnvironmentSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Deployment> deploy(int projectId, String environment,
      {String provider = 'local'}) async {
    final data = await _api.post('projects/$projectId/deployments/',
        body: {'environment': environment, 'provider': provider});
    return Deployment.fromJson(data as Map<String, dynamic>);
  }
}

final deploymentsRepositoryProvider = Provider<DeploymentsRepository>(
  (ref) => DeploymentsRepository(ref.watch(apiClientProvider)),
);

final environmentsProvider =
    FutureProvider.family<List<EnvironmentSummary>, int>((ref, projectId) {
  return ref.watch(deploymentsRepositoryProvider).environments(projectId);
});
