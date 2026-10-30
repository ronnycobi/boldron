import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'quality_repository.dart';

/// Security (spec §8) on mobile: the real scan ledger — findings by severity, honest
/// status (a project with no code reads skipped, never a fake pass), deploy gate.
class ProjectSecurityScreen extends ConsumerWidget {
  final int projectId;
  const ProjectSecurityScreen({super.key, required this.projectId});

  Color _sevColor(BuildContext context, String sev) {
    final scheme = Theme.of(context).colorScheme;
    if (sev == 'high') return scheme.error;
    if (sev == 'medium') return Colors.orange;
    return scheme.onSurfaceVariant;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final security = ref.watch(securityProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Security')),
      body: security.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (s) {
          final latest = (s['latest'] as Map?)?.cast<String, dynamic>();
          final findings = ((latest?['findings'] as List?) ?? []).cast<dynamic>();
          final scans = ((s['scans'] as List?) ?? []).cast<dynamic>();
          final ok = (s['ok'] ?? false) as bool;
          final blocks = (latest?['blocks_deploy'] ?? false) as bool;
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(securityProvider(projectId).future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(children: [
                          Icon(Icons.circle, size: 12,
                              color: ok ? Colors.green : Theme.of(context).colorScheme.error),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(ok ? 'No high-severity findings' : 'Needs attention',
                                style: Theme.of(context).textTheme.titleMedium),
                          ),
                        ]),
                        const SizedBox(height: 4),
                        Text(latest != null ? '${latest['summary']}' : 'No scans yet.',
                            style: Theme.of(context).textTheme.bodySmall),
                        if (blocks)
                          Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(
                                'A production deploy is blocked until the high-severity '
                                'findings are resolved.',
                                style: Theme.of(context).textTheme.bodySmall),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: () => _run(context, ref,
                      () => ref.read(qualityRepositoryProvider).runScan(projectId)),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Run scan'),
                ),
                if (findings.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text('Findings', style: Theme.of(context).textTheme.titleSmall),
                  for (final f in findings)
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(Icons.warning_amber_rounded,
                          color: _sevColor(context, '${(f as Map)['severity']}')),
                      title: Text('${f['message']}'),
                      subtitle: Text('${f['category']} · ${f['path']}:${f['line']}'),
                    ),
                ],
                const SizedBox(height: 16),
                Text('Scan history', style: Theme.of(context).textTheme.titleSmall),
                for (final sc in scans)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text('${(sc as Map)['summary']}'),
                    subtitle: Text('${sc['trigger']} · ${sc['created_at']}'),
                    trailing: Text('${sc['status']}'),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _run(
      BuildContext context, WidgetRef ref, Future<void> Function() action) async {
    try {
      await action();
      ref.invalidate(securityProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
