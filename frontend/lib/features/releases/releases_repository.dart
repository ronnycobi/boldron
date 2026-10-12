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

  String _store(int appId, String provider) =>
      'mobile-apps/$appId/stores/$provider';

  Future<StoreListing> listing(int appId, String provider) async {
    final data = await _api.get('${_store(appId, provider)}/listing/');
    return StoreListing.fromJson(data as Map<String, dynamic>);
  }

  Future<void> generateListing(int appId, String provider) =>
      _api.post('${_store(appId, provider)}/listing/');

  Future<void> approveListing(int appId, String provider) =>
      _api.post('${_store(appId, provider)}/listing/approve/');

  Future<void> generateScreenshots(int appId, String provider) =>
      _api.post('${_store(appId, provider)}/screenshots/');

  Future<void> approveScreenshots(int appId, String provider) =>
      _api.post('${_store(appId, provider)}/screenshots/approve/');
}

class StoreListing {
  final String provider;
  final String providerLabel;
  final StoreMetadata? metadata;
  final List<StoreScreenshot> screenshots;

  const StoreListing({
    required this.provider,
    required this.providerLabel,
    required this.metadata,
    required this.screenshots,
  });

  factory StoreListing.fromJson(Map<String, dynamic> j) => StoreListing(
        provider: (j['provider'] ?? '') as String,
        providerLabel: (j['provider_label'] ?? '') as String,
        metadata: j['metadata'] == null
            ? null
            : StoreMetadata.fromJson(j['metadata'] as Map<String, dynamic>),
        screenshots: ((j['screenshots'] as List?) ?? [])
            .map((s) => StoreScreenshot.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}

class StoreMetadata {
  final String appName;
  final String shortDescription;
  final String fullDescription;
  final String keywords;
  final bool aiGenerated;
  final bool approved;
  final String source;

  const StoreMetadata({
    required this.appName,
    required this.shortDescription,
    required this.fullDescription,
    required this.keywords,
    required this.aiGenerated,
    required this.approved,
    required this.source,
  });

  factory StoreMetadata.fromJson(Map<String, dynamic> j) => StoreMetadata(
        appName: (j['app_name'] ?? '') as String,
        shortDescription: (j['short_description'] ?? '') as String,
        fullDescription: (j['full_description'] ?? '') as String,
        keywords: (j['keywords'] ?? '') as String,
        aiGenerated: (j['ai_generated'] ?? false) as bool,
        approved: (j['approved'] ?? false) as bool,
        source: (j['source'] ?? '') as String,
      );
}

class StoreScreenshot {
  final int id;
  final String screenName;
  final String caption;
  final bool approved;

  const StoreScreenshot({
    required this.id,
    required this.screenName,
    required this.caption,
    required this.approved,
  });

  factory StoreScreenshot.fromJson(Map<String, dynamic> j) => StoreScreenshot(
        id: j['id'] as int,
        screenName: (j['screen_name'] ?? '') as String,
        caption: (j['caption'] ?? '') as String,
        approved: (j['approved'] ?? false) as bool,
      );
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

/// A store listing keyed by (appId, provider), e.g. (12, 'google_play').
final storeListingProvider =
    FutureProvider.family<StoreListing, (int, String)>((ref, key) {
  return ref.watch(releasesRepositoryProvider).listing(key.$1, key.$2);
});
