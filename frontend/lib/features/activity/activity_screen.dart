import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'activity_repository.dart';

class ActivityScreen extends ConsumerWidget {
  const ActivityScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final feed = ref.watch(activityFeedProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Activity')),
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(activityFeedProvider.future),
        child: feed.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 100),
            Center(child: Text(e.toString(), textAlign: TextAlign.center)),
          ]),
          data: (items) => items.isEmpty
              ? ListView(children: const [
                  SizedBox(height: 120),
                  Center(child: Text('Nothing has happened yet.')),
                ])
              : ListView.separated(
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final it = items[i];
                    return ListTile(
                      leading: const Icon(Icons.bolt_outlined),
                      title: Text(it.title),
                      subtitle: Text(
                        [
                          if (it.detail.isNotEmpty) it.detail,
                          if (it.organizationName.isNotEmpty) it.organizationName,
                        ].join(' · '),
                      ),
                      trailing: Text(
                        _ago(it.createdAt),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    );
                  },
                ),
        ),
      ),
    );
  }

  String _ago(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'now';
    if (d.inHours < 1) return '${d.inMinutes}m';
    if (d.inDays < 1) return '${d.inHours}h';
    return '${d.inDays}d';
  }
}
