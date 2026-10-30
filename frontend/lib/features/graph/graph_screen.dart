import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'graph_repository.dart';

/// The Application Graph (spec §4): how the parts of the app connect, grouped by
/// kind. Tapping a part opens its Dependency Intelligence (spec §5) — what would
/// be affected if it changed. Honest: composed from real project data only.
class GraphScreen extends ConsumerWidget {
  final int projectId;
  const GraphScreen({super.key, required this.projectId});

  static const _typeLabels = <String, String>{
    'application': 'Application',
    'feature': 'Features',
    'infrastructure': 'Infrastructure & hosting',
    'integration': 'Integrations',
    'security': 'Security & trust',
    'screen': 'Web screens',
    'mobile_screen': 'Mobile screens',
    'api': 'APIs',
    'entity': 'Data entities',
    'requirement': 'Requirements',
    'business_rule': 'Business rules',
    'environment': 'Environments',
    'mobile_platform': 'Mobile platforms',
  };
  static const _typeOrder = [
    'application', 'feature', 'infrastructure', 'integration', 'security',
    'screen', 'mobile_screen', 'api', 'entity', 'requirement',
    'business_rule', 'environment', 'mobile_platform',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final graph = ref.watch(graphProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Application graph')),
      body: graph.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (g) {
          final nodes =
              ((g['nodes'] as List?) ?? []).cast<Map<String, dynamic>>();
          final stats = (g['stats'] as Map?)?.cast<String, dynamic>() ?? {};
          final byType = <String, List<Map<String, dynamic>>>{};
          for (final n in nodes) {
            byType.putIfAbsent('${n['type']}', () => []).add(n);
          }
          // Build a label map for "needs X" hints.
          final labels = {for (final n in nodes) '${n['id']}': '${n['label']}'};
          final edges =
              ((g['edges'] as List?) ?? []).cast<Map<String, dynamic>>();
          const depKinds = {'requires', 'uses', 'runs_on', 'part_of', 'stored_in'};
          final depsOf = <String, List<String>>{};
          for (final e in edges) {
            if (depKinds.contains(e['kind'])) {
              depsOf
                  .putIfAbsent('${e['source']}', () => [])
                  .add(labels['${e['target']}'] ?? '${e['target']}');
            }
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                child: Row(
                  children: [
                    Text('${stats['nodes'] ?? nodes.length}',
                        style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(width: 4),
                    const Text('parts'),
                    const SizedBox(width: 20),
                    Text('${stats['edges'] ?? edges.length}',
                        style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(width: 4),
                    const Text('connections'),
                  ],
                ),
              ),
              const SizedBox(height: 6),
              Text('Tap a part to see what depends on it.',
                  style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 12),
              for (final t in _typeOrder)
                if (byType[t] != null)
                  _group(context, _typeLabels[t] ?? t, byType[t]!, depsOf),
            ],
          );
        },
      ),
    );
  }

  Widget _group(BuildContext context, String label,
      List<Map<String, dynamic>> nodes, Map<String, List<String>> depsOf) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(label, style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                Text('${nodes.length}',
                    style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 4),
            for (final n in nodes)
              _NodeRow(
                node: n,
                deps: depsOf['${n['id']}'] ?? const [],
                onTap: () => _showImpact(context, n),
              ),
          ],
        ),
      ),
    );
  }

  void _showImpact(BuildContext context, Map<String, dynamic> node) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _ImpactSheet(projectId: projectId, node: node),
    );
  }
}

class _NodeRow extends StatelessWidget {
  final Map<String, dynamic> node;
  final List<String> deps;
  final VoidCallback onTap;
  const _NodeRow({required this.node, required this.deps, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final coming = node['available'] == false;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(child: Text('${node['label']}')),
                      if (coming) ...[
                        const SizedBox(width: 6),
                        Text('COMING',
                            style: Theme.of(context).textTheme.labelSmall),
                      ],
                    ],
                  ),
                  if (deps.isNotEmpty)
                    Text('needs ${deps.join(', ')}',
                        style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, size: 18),
          ],
        ),
      ),
    );
  }
}

/// Dependency Intelligence (spec §5) for one node: what is affected if it
/// changes, and what it depends on.
class _ImpactSheet extends ConsumerWidget {
  final int projectId;
  final Map<String, dynamic> node;
  const _ImpactSheet({required this.projectId, required this.node});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final report = ref.watch(_reportProvider((projectId, '${node['id']}')));
    return Padding(
      padding: EdgeInsets.only(
        left: 16, right: 16, top: 4,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: report.when(
        loading: () => const Padding(
            padding: EdgeInsets.all(28),
            child: Center(child: CircularProgressIndicator())),
        error: (e, _) => Padding(
            padding: const EdgeInsets.all(20), child: Text(e.toString())),
        data: (r) {
          final dependents =
              ((r['dependents'] as List?) ?? []).cast<Map<String, dynamic>>();
          final dependsOn =
              ((r['depends_on'] as List?) ?? []).cast<Map<String, dynamic>>();
          final count = r['impact_count'] ?? dependents.length;
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${node['label']}',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 4),
              Text(
                  'Changing this would affect $count other part${count == 1 ? '' : 's'} of your app.',
                  style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 16),
              Text('Affected if this changes',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (dependents.isEmpty)
                const Text('Nothing depends on this.')
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final d in dependents) Chip(label: Text('${d['label']}')),
                  ],
                ),
              const SizedBox(height: 16),
              Text('This depends on',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (dependsOn.isEmpty)
                const Text('Self-contained — depends on nothing.')
              else
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final d in dependsOn)
                      Chip(
                        label: Text('${d['label']}'),
                        visualDensity: VisualDensity.compact,
                      ),
                  ],
                ),
            ],
          );
        },
      ),
    );
  }
}

final _reportProvider = FutureProvider.family<Map<String, dynamic>,
    (int, String)>((ref, args) {
  return ref.watch(graphRepositoryProvider).dependencies(args.$1, args.$2);
});
