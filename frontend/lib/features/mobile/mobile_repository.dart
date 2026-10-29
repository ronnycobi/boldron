import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// One capability in a mobile plan, with its honest status.
class MobileCapability {
  final String id;
  final String name;
  final String status; // generated / gated / planned
  final bool generated;
  final String summary;
  final Map<String, dynamic> platformNotes;

  const MobileCapability({
    required this.id,
    required this.name,
    required this.status,
    required this.generated,
    required this.summary,
    this.platformNotes = const {},
  });

  factory MobileCapability.fromJson(Map<String, dynamic> j) => MobileCapability(
        id: (j['id'] ?? '') as String,
        name: (j['name'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        generated: (j['generated'] ?? false) as bool,
        summary: (j['summary'] ?? '') as String,
        platformNotes:
            ((j['platform_notes'] as Map?) ?? {}).cast<String, dynamic>(),
      );
}

class MobileCapabilityGroup {
  final String group;
  final List<MobileCapability> items;
  const MobileCapabilityGroup({required this.group, required this.items});

  factory MobileCapabilityGroup.fromJson(Map<String, dynamic> j) =>
      MobileCapabilityGroup(
        group: (j['group'] ?? '') as String,
        items: ((j['items'] as List?) ?? [])
            .map((i) => MobileCapability.fromJson(i as Map<String, dynamic>))
            .toList(),
      );
}

class MobilePermission {
  final String id;
  final String name;
  final String rationale;
  const MobilePermission(
      {required this.id, required this.name, required this.rationale});

  factory MobilePermission.fromJson(Map<String, dynamic> j) => MobilePermission(
        id: (j['id'] ?? '') as String,
        name: (j['name'] ?? '') as String,
        rationale: (j['rationale'] ?? '') as String,
      );
}

class MobilePlan {
  final List<({String id, String name})> platforms;
  final List<MobileCapabilityGroup> groups;
  final List<MobilePermission> permissions;
  final int generatedCount;
  final int gatedCount;
  final int plannedCount;
  final List<String> gatedNames;
  final String disclosure;

  const MobilePlan({
    required this.platforms,
    required this.groups,
    required this.permissions,
    required this.generatedCount,
    required this.gatedCount,
    required this.plannedCount,
    required this.gatedNames,
    required this.disclosure,
  });

  factory MobilePlan.fromJson(Map<String, dynamic> j) {
    final summary = ((j['summary'] as Map?) ?? {}).cast<String, dynamic>();
    return MobilePlan(
      platforms: ((j['platforms'] as List?) ?? [])
          .map((p) => (
                id: ((p as Map)['id'] ?? '') as String,
                name: (p['name'] ?? '') as String
              ))
          .toList(),
      groups: ((j['groups'] as List?) ?? [])
          .map((g) => MobileCapabilityGroup.fromJson(g as Map<String, dynamic>))
          .toList(),
      permissions: ((j['permissions'] as List?) ?? [])
          .map((p) => MobilePermission.fromJson(p as Map<String, dynamic>))
          .toList(),
      generatedCount: (summary['generated_count'] ?? 0) as int,
      gatedCount: (summary['gated_count'] ?? 0) as int,
      plannedCount: (summary['planned_count'] ?? 0) as int,
      gatedNames: ((summary['gated_names'] as List?) ?? [])
          .map((e) => e.toString())
          .toList(),
      disclosure: (j['disclosure'] ?? '') as String,
    );
  }
}

class MobileRepository {
  final ApiClient _api;
  MobileRepository(this._api);

  Future<MobilePlan> plan(String brief, {List<String>? platforms}) async {
    final data = await _api.post('mobile/plan/', body: {
      'brief': brief,
      if (platforms != null) 'platforms': platforms,
    });
    return MobilePlan.fromJson((data as Map).cast<String, dynamic>());
  }
}

final mobileRepositoryProvider = Provider<MobileRepository>(
  (ref) => MobileRepository(ref.watch(apiClientProvider)),
);

/// All three platforms the engine targets.
const kMobilePlatforms = <({String id, String name})>[
  (id: 'ios', name: 'iOS'),
  (id: 'android', name: 'Android'),
  (id: 'huawei', name: 'Huawei AppGallery'),
];
