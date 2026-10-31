import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'performance_repository.dart';

/// Performance intelligence (spec §41): per-surface percentiles from real timing
/// samples, slowest first, with budget flags. Empty until the app reports timings.
class PerformanceScreen extends ConsumerWidget {
  final int projectId;
  const PerformanceScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(performanceProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Performance')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final report = (d['report'] as Map?)?.cast<String, dynamic>() ?? {};
          final labels =
              ((report['labels'] as List?) ?? []).cast<Map<String, dynamic>>();
          final overall =
              (report['overall'] as Map?)?.cast<String, dynamic>() ?? {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text(overall['p95'] == null ? '—' : '${overall['p95']}ms',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 8),
                    const Expanded(child: Text('overall p95')),
                    Text('${summary['samples'] ?? 0} samples',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (labels.isEmpty)
                const PanelCard(
                    child: Text('No performance samples yet. Your app can report '
                        'timings and they will appear here.'))
              else
                PanelCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Surfaces (slowest first)',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 8),
                      for (final r in labels) _SurfaceRow(row: r),
                    ],
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _SurfaceRow extends StatelessWidget {
  final Map<String, dynamic> row;
  const _SurfaceRow({required this.row});

  @override
  Widget build(BuildContext context) {
    final over = (row['over_budget'] ?? false) as bool;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${row['label']}',
                    style: TextStyle(
                        fontFamily: 'monospace',
                        color: over ? Colors.red : null)),
                Text(
                    'p50 ${row['p50']}ms · max ${row['max']}ms · ${row['count']} samples'
                    '${row['budget'] != null ? ' · budget ${row['budget']}ms' : ''}',
                    style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          Text('${row['p95']}ms${over ? ' ⚠' : ''}',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: over ? Colors.red : null,
                  fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
