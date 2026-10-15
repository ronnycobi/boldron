import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'team_repository.dart';

/// Read-only organization audit log. The server gates this to managers, so a
/// member hits a 403 that surfaces here as an error.
class OrgAuditScreen extends ConsumerWidget {
  final int orgId;
  const OrgAuditScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final audit = ref.watch(orgAuditProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Audit log')),
      body: audit.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'This log is available to owners and admins.',
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
          ),
        ),
        data: (events) => events.isEmpty
            ? const Center(child: Text('No audit events yet.'))
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: events.length,
                separatorBuilder: (_, __) => const Divider(height: 14),
                itemBuilder: (_, i) {
                  final e = events[i];
                  final when = '${e['created_at'] ?? ''}';
                  return ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text('${e['action']}',
                        style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                    subtitle: Text([
                      if ('${e['summary'] ?? ''}'.isNotEmpty) '${e['summary']}',
                      '${e['actor'] ?? 'system'}',
                      if (when.length >= 19) when.substring(0, 19),
                    ].join(' · ')),
                  );
                },
              ),
      ),
    );
  }
}
