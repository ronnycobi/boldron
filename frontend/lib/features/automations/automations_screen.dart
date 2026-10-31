import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'automations_repository.dart';

/// Automations (spec §10-11): the project's trigger→conditions→actions rules,
/// each with its recent run history showing honest per-action outcomes. A person
/// changes status and test-runs; actions are never faked.
class AutomationsScreen extends ConsumerWidget {
  final int projectId;
  const AutomationsScreen({super.key, required this.projectId});

  static const _statuses = {
    'draft': 'Draft',
    'active': 'Active',
    'paused': 'Paused',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(automationsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Automations')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final items =
              ((d['automations'] as List?) ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text('${summary['active'] ?? 0}',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 6),
                    const Text('active'),
                    const Spacer(),
                    Text('${summary['runs'] ?? 0} run(s) recorded',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (items.isEmpty)
                const PanelCard(
                    child: Text('No automations yet. Create one from the web '
                        'builder to react to project events.')),
              for (final wf in items)
                _AutomationCard(
                  wf: wf,
                  onStatus: (s) => _setStatus(context, ref, wf['id'] as int, s),
                  onTest: () => _test(context, ref, wf),
                ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _setStatus(
      BuildContext context, WidgetRef ref, int id, String status) async {
    try {
      await ref.read(automationsRepositoryProvider).setStatus(id, status);
      ref.invalidate(automationsProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _test(
      BuildContext context, WidgetRef ref, Map<String, dynamic> wf) async {
    try {
      final run =
          await ref.read(automationsRepositoryProvider).testRun(wf['id'] as int, {});
      ref.invalidate(automationsProvider(projectId));
      if (context.mounted) {
        final results = ((run['results'] as List?) ?? [])
            .map((r) => '${(r as Map)['action']}: ${r['outcome']}')
            .join(', ');
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Test run ${run['status']}'
                '${results.isNotEmpty ? ' — $results' : ''}')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _AutomationCard extends StatelessWidget {
  final Map<String, dynamic> wf;
  final ValueChanged<String> onStatus;
  final VoidCallback onTest;
  const _AutomationCard(
      {required this.wf, required this.onStatus, required this.onTest});

  Color _outcomeColor(String o) => switch (o) {
        'done' => Colors.green,
        'skipped' => Colors.grey,
        _ => Colors.red,
      };

  @override
  Widget build(BuildContext context) {
    final conditions = (wf['conditions'] as List?) ?? [];
    final actions = (wf['actions'] as List?) ?? [];
    final runs = ((wf['runs'] as List?) ?? []).cast<Map<String, dynamic>>();
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('${wf['name']}',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                IconButton(
                  tooltip: 'Test run',
                  icon: const Icon(Icons.play_arrow_outlined, size: 20),
                  onPressed: onTest,
                ),
                PopupMenuButton<String>(
                  tooltip: 'Set status',
                  icon: const Icon(Icons.more_vert, size: 18),
                  onSelected: onStatus,
                  itemBuilder: (_) => [
                    for (final e in AutomationsScreen._statuses.entries)
                      PopupMenuItem(value: e.key, child: Text(e.value)),
                  ],
                ),
              ],
            ),
            Wrap(
              spacing: 6,
              children: [
                Chip(
                    label: Text('${wf['status_label']}'),
                    visualDensity: VisualDensity.compact),
                Chip(
                    label: Text('when ${wf['trigger_label']}'),
                    visualDensity: VisualDensity.compact),
              ],
            ),
            Text(
                '${conditions.length} condition(s) · ${actions.length} action(s) · '
                '${wf['run_count']} run(s)',
                style: Theme.of(context).textTheme.bodySmall),
            if (runs.isNotEmpty) ...[
              const Divider(height: 18),
              Text('Recent runs',
                  style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(height: 4),
              for (final run in runs.take(3))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${run['status']}',
                          style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Wrap(
                          spacing: 4,
                          children: [
                            for (final r
                                in ((run['results'] as List?) ?? []))
                              Text(
                                '${(r as Map)['action']}:${r['outcome']}',
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(
                                        color: _outcomeColor('${r['outcome']}')),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
