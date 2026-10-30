import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'operations_repository.dart';

/// The Operations Center (spec §10) on mobile: a live, customer-safe health view
/// composed by the backend. Every figure is a real record; "—" means no signal.
class OperationsScreen extends ConsumerWidget {
  final int projectId;
  const OperationsScreen({super.key, required this.projectId});

  Color _statusColor(BuildContext context, String status) {
    final scheme = Theme.of(context).colorScheme;
    switch (status) {
      case 'healthy':
        return Colors.green;
      case 'down':
      case 'degraded':
        return scheme.error;
      default:
        return scheme.onSurfaceVariant;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ops = ref.watch(operationsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Operations')),
      body: ops.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (o) {
          final uptime = (o['uptime'] as Map?)?.cast<String, dynamic>();
          final traffic = (o['traffic'] as Map?)?.cast<String, dynamic>();
          final deploys = (o['deployments'] as Map?)?.cast<String, dynamic>() ?? {};
          final jobs = (o['jobs'] as Map?)?.cast<String, dynamic>() ?? {};
          final storage = (o['storage'] as Map?)?.cast<String, dynamic>() ?? {};
          final quality = (o['quality'] as Map?)?.cast<String, dynamic>() ?? {};
          final incidents = (o['incidents'] as Map?)?.cast<String, dynamic>() ?? {};
          final status = (o['status'] ?? 'unknown') as String;
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(operationsProvider(projectId).future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Row(
                  children: [
                    Icon(Icons.circle, size: 12, color: _statusColor(context, status)),
                    const SizedBox(width: 8),
                    Text('${o['status_label']}',
                        style: Theme.of(context).textTheme.titleLarge),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  'A live health view. Every figure is a real record; "—" means no '
                  'signal yet, never a fake green.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 16),
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  childAspectRatio: 2.3,
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  children: [
                    _stat(context, 'Uptime',
                        uptime?['uptime_pct'] != null ? '${uptime!['uptime_pct']}%' : '—',
                        uptime != null ? '${uptime['incidents']} incidents' : 'not monitored'),
                    _stat(context, 'Response',
                        uptime?['avg_response_ms'] != null ? '${uptime!['avg_response_ms']}ms' : '—', ''),
                    _stat(context, 'Traffic 30d',
                        traffic != null ? '${traffic['pageviews']}' : '—',
                        traffic != null ? '${traffic['visitors']} visitors' : ''),
                    _stat(context, 'Storage', '${storage['display'] ?? '—'}', ''),
                    _stat(context, 'Deploys', '${deploys['total'] ?? 0}',
                        deploys['latest_status'] != null ? 'last: ${deploys['latest_status']}' : 'none'),
                    _stat(context, 'Jobs',
                        '${(jobs['running'] ?? 0) + (jobs['queued'] ?? 0)}',
                        '${jobs['failed'] ?? 0} failed'),
                  ],
                ),
                const SizedBox(height: 16),
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: const Icon(Icons.verified_outlined),
                        title: const Text('Tests'),
                        trailing: _chip(context, '${quality['tests'] ?? '—'}'),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: const Icon(Icons.shield_outlined),
                        title: const Text('Security'),
                        trailing: _chip(context, '${quality['security'] ?? '—'}'),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: const Icon(Icons.report_outlined),
                        title: const Text('Incidents'),
                        trailing: Text('${incidents['open'] ?? 0} open'),
                        onTap: () =>
                            context.push('/projects/$projectId/incidents'),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                FilledButton.tonalIcon(
                  onPressed: () => context.push('/projects/$projectId/incidents'),
                  icon: const Icon(Icons.report_outlined),
                  label: const Text('View incidents'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _stat(BuildContext context, String label, String value, String sub) => Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(label.toUpperCase(),
                  style: Theme.of(context).textTheme.labelSmall),
              Text(value, style: Theme.of(context).textTheme.titleLarge),
              if (sub.isNotEmpty)
                Text(sub, style: Theme.of(context).textTheme.bodySmall,
                    maxLines: 1, overflow: TextOverflow.ellipsis),
            ],
          ),
        ),
      );

  Widget _chip(BuildContext context, String text) {
    final good = text == 'passed' || text == 'clean';
    final bad = text == 'failed' || text == 'blocked';
    final scheme = Theme.of(context).colorScheme;
    return Chip(
      label: Text(text),
      visualDensity: VisualDensity.compact,
      backgroundColor: good
          ? Colors.green.withOpacity(.18)
          : bad
              ? scheme.errorContainer
              : scheme.surfaceVariant,
    );
  }
}
