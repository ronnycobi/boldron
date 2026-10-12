import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class MobileApp {
  final int id;
  final String name;
  final String packageId;
  final String bundleId;
  final String version;
  final int buildNumber;
  final List<Map<String, dynamic>> storeApps;
  final List<Map<String, dynamic>> builds;

  const MobileApp({
    required this.id,
    required this.name,
    required this.packageId,
    required this.bundleId,
    required this.version,
    required this.buildNumber,
    this.storeApps = const [],
    this.builds = const [],
  });

  factory MobileApp.fromJson(Map<String, dynamic> j) => MobileApp(
        id: j['id'] as int,
        name: (j['name'] ?? '') as String,
        packageId: (j['package_identifier'] ?? '') as String,
        bundleId: (j['bundle_identifier'] ?? '') as String,
        version: (j['version'] ?? '') as String,
        buildNumber: (j['build_number'] ?? 0) as int,
        storeApps: ((j['store_apps'] as List?) ?? [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList(),
        builds: ((j['builds'] as List?) ?? [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList(),
      );
}

class ReleasesRepository {
  final ApiClient _api;
  ReleasesRepository(this._api);

  Future<List<MobileApp>> apps(int projectId) async {
    final data = await _api.get('projects/$projectId/mobile-apps/');
    return (data as List)
        .map((a) => MobileApp.fromJson(a as Map<String, dynamic>))
        .toList();
  }

  Future<MobileApp> create(int projectId, String name,
      {String packageId = '', String bundleId = ''}) async {
    final data = await _api.post('projects/$projectId/mobile-apps/', body: {
      'name': name,
      'package_identifier': packageId,
      'bundle_identifier': bundleId,
    });
    return MobileApp.fromJson(data as Map<String, dynamic>);
  }

  Future<MobileApp> app(int appId) async {
    final data = await _api.get('mobile-apps/$appId/');
    return MobileApp.fromJson(data as Map<String, dynamic>);
  }

  Future<List<Map<String, dynamic>>> providers() async {
    final data = await _api.get('release/providers/');
    return (data as List).map((e) => (e as Map).cast<String, dynamic>()).toList();
  }
}

final releasesRepositoryProvider = Provider<ReleasesRepository>(
  (ref) => ReleasesRepository(ref.watch(apiClientProvider)),
);

final mobileAppsProvider =
    FutureProvider.family<List<MobileApp>, int>((ref, projectId) {
  return ref.watch(releasesRepositoryProvider).apps(projectId);
});

final mobileAppProvider =
    FutureProvider.family<MobileApp, int>((ref, appId) {
  return ref.watch(releasesRepositoryProvider).app(appId);
});
