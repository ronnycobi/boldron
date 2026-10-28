import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'team_repository.dart';

/// Custom domains across the org's projects — real records, real DNS status.
class OrgDomainsScreen extends ConsumerWidget {
  final int orgId;
  const OrgDomainsScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final domains = ref.watch(orgDomainsProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Domains')),
      body: domains.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (list) => list.isEmpty
            ? const Center(child: Text('No custom domains yet.'))
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  for (final d in list)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('${d['hostname']}',
                          style: const TextStyle(fontFamily: 'monospace')),
                      subtitle: Text('${d['project']}'),
                      trailing: Text(
                        (d['verified'] ?? false) as bool
                            ? 'Verified'
                            : '${d['status']}',
                        style: TextStyle(
                            color: (d['verified'] ?? false) as bool
                                ? const Color(0xFF4AD295)
                                : const Color(0xFFF5C454)),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}
