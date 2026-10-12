import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class ActivityItem {
  final int id;
  final String title;
  final String detail;
  final String organizationName;
  final String actor;
  final DateTime createdAt;

  const ActivityItem({
    required this.id,
    required this.title,
    required this.detail,
    required this.organizationName,
    required this.actor,
    required this.createdAt,
  });

  factory ActivityItem.fromJson(Map<String, dynamic> json) => ActivityItem(
        id: json['id'] as int,
        title: (json['title'] ?? '') as String,
        detail: (json['detail'] ?? '') as String,
        organizationName: (json['organization_name'] ?? '') as String,
        actor: (json['actor'] ?? '') as String,
        createdAt: DateTime.tryParse((json['created_at'] ?? '') as String) ??
            DateTime.now(),
      );
}

class ActivityRepository {
  final ApiClient _api;
  ActivityRepository(this._api);

  Future<List<ActivityItem>> feed() async {
    final data = await _api.get('notifications/');
    final list = (data as Map)['notifications'] as List;
    return list
        .map((e) => ActivityItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}

final activityRepositoryProvider = Provider<ActivityRepository>(
  (ref) => ActivityRepository(ref.watch(apiClientProvider)),
);

final activityFeedProvider = FutureProvider<List<ActivityItem>>(
  (ref) => ref.watch(activityRepositoryProvider).feed(),
);
