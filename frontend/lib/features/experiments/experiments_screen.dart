import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'experiments_repository.dart';

/// A/B experiments (spec §20): variants with real exposure/conversion results and
/// an honest significance verdict. A person starts/stops; results are never faked.
class ExperimentsScreen extends ConsumerWidget {
  final int projectId;
  const ExperimentsScreen({super.key, required this.projectId});

  static const _statuses = {
    'draft': 'Draft',
    'running': 'Running',
    'stopped': 'Stopped',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(experimentsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('A/B experiments')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final items =
              ((d['experiments'] as List?) ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text('${summary['running'] ?? 0}',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 6),
                    const Text('running'),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (items.isEmpty)
                const PanelCard(
                    child: Text('No experiments yet. Create one from the web to '
                        'split traffic and measure what converts.')),
              for (final e in items)
                _ExperimentCard(
                  experiment: e,
                  onStatus: (s) =>
                      _setStatus(context, ref, e['id'] as int, s),
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
      await ref.read(experimentsRepositoryProvider).setStatus(id, status);
      ref.invalidate(experimentsProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _ExperimentCard extends StatelessWidget {
  final Map<String, dynamic> experiment;
  final ValueChanged<String> onStatus;
  const _ExperimentCard({required this.experiment, required this.onStatus});

  @override
  Widget build(BuildContext context) {
    final results =
        (experiment['results'] as Map?)?.cast<String, dynamic>() ?? {};
    final variants =
        ((results['variants'] as List?) ?? []).cast<Map<String, dynamic>>();
    final assessment =
        (results['assessment'] as Map?)?.cast<String, dynamic>() ?? {};
    final leader = assessment['leader'];
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                      '${experiment['name']?.toString().isNotEmpty == true ? experiment['name'] : experiment['key']}',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                PopupMenuButton<String>(
                  tooltip: 'Set status',
                  icon: const Icon(Icons.more_vert, size: 18),
                  onSelected: onStatus,
                  itemBuilder: (_) => [
                    for (final e in ExperimentsScreen._statuses.entries)
                      PopupMenuItem(value: e.key, child: Text(e.value)),
                  ],
                ),
              ],
            ),
            Chip(
                label: Text('${experiment['status_label']}'),
                visualDensity: VisualDensity.compact),
            const SizedBox(height: 8),
            for (final v in variants)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${v['name']}${v['key'] == leader ? ' 🏆' : ''}',
                        style: v['key'] == leader
                            ? const TextStyle(fontWeight: FontWeight.bold)
                            : null,
                      ),
                    ),
                    Text(
                        '${v['conversions']}/${v['exposures']} · ${v['rate_pct']}%',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
            const SizedBox(height: 6),
            Text('${assessment['reason'] ?? ''}',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
