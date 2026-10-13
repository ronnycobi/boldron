import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class SiteVersion {
  final int id;
  final String version;
  final String state;
  final String url;
  final bool isCurrent;

  const SiteVersion({
    required this.id,
    required this.version,
    required this.state,
    required this.url,
    required this.isCurrent,
  });

  factory SiteVersion.fromJson(Map<String, dynamic> j) => SiteVersion(
        id: j['id'] as int,
        version: (j['version'] ?? '') as String,
        state: (j['state'] ?? '') as String,
        url: (j['url'] ?? '') as String,
        isCurrent: (j['is_current'] ?? false) as bool,
      );
}

class CustomDomain {
  final int id;
  final String hostname;
  final String verificationStatus;
  final String sslStatus;
  final bool isLive;

  const CustomDomain({
    required this.id,
    required this.hostname,
    required this.verificationStatus,
    required this.sslStatus,
    required this.isLive,
  });

  factory CustomDomain.fromJson(Map<String, dynamic> j) => CustomDomain(
        id: j['id'] as int,
        hostname: (j['hostname'] ?? '') as String,
        verificationStatus: (j['verification_status'] ?? '') as String,
        sslStatus: (j['ssl_status'] ?? '') as String,
        isLive: (j['is_live'] ?? false) as bool,
      );
}

class WebsiteInfo {
  final String subdomain;
  final String siteType;
  final SiteVersion? current;
  final String url;
  final List<CustomDomain> domains;

  const WebsiteInfo({
    required this.subdomain,
    required this.siteType,
    required this.current,
    required this.url,
    required this.domains,
  });

  factory WebsiteInfo.fromJson(Map<String, dynamic> j) => WebsiteInfo(
        subdomain: (j['subdomain'] ?? '') as String,
        siteType: (j['site_type'] ?? '') as String,
        current: j['current_version'] == null
            ? null
            : SiteVersion.fromJson(j['current_version'] as Map<String, dynamic>),
        url: (j['url'] ?? '') as String,
        domains: ((j['domains'] as List?) ?? [])
            .map((d) => CustomDomain.fromJson(d as Map<String, dynamic>))
            .toList(),
      );
}

class WebsiteRepository {
  final ApiClient _api;
  WebsiteRepository(this._api);

  Future<WebsiteInfo> info(int projectId) async {
    final data = await _api.get('projects/$projectId/website/');
    return WebsiteInfo.fromJson(data as Map<String, dynamic>);
  }

  Future<void> publish(int projectId) =>
      _api.post('projects/$projectId/website/publish/');

  Future<void> rollback(int projectId) =>
      _api.post('projects/$projectId/website/rollback/');

  Future<List<SiteVersion>> versions(int projectId) async {
    final data = await _api.get('projects/$projectId/website/versions/');
    return (data as List)
        .map((v) => SiteVersion.fromJson(v as Map<String, dynamic>))
        .toList();
  }

  Future<void> connectDomain(int projectId, String hostname) =>
      _api.post('projects/$projectId/website/domains/',
          body: {'hostname': hostname});

  Future<Map<String, dynamic>> monitoring(int projectId) async {
    final data = await _api.get('projects/$projectId/website/monitoring/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> runCheck(int projectId) async {
    final data = await _api.post('projects/$projectId/website/monitoring/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> analytics(int projectId) async {
    final data = await _api.get('projects/$projectId/website/analytics/');
    return (data as Map).cast<String, dynamic>();
  }
}

final websiteRepositoryProvider = Provider<WebsiteRepository>(
  (ref) => WebsiteRepository(ref.watch(apiClientProvider)),
);

final websiteProvider =
    FutureProvider.family<WebsiteInfo, int>((ref, projectId) {
  return ref.watch(websiteRepositoryProvider).info(projectId);
});

final monitoringProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(websiteRepositoryProvider).monitoring(projectId);
});

final analyticsProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, projectId) {
  return ref.watch(websiteRepositoryProvider).analytics(projectId);
});
