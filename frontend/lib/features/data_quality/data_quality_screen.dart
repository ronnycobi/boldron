import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'data_quality_repository.dart';

/// Data quality (spec §9): each dataset's rules and the latest real check score.
class DataQualityScreen extends ConsumerWidget {
  final int projectId;
  const DataQualityScreen({super.key, required this.projectId});

  static Color _scoreColor(int s) =>
      s >= 90 ? Colors.green : (s >= 60 ? const Color(0xFFC99A00) : Colors.red);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(dataQualityProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Data quality')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final datasets =
              ((d['datasets'] as List?) ?? []).cast<Map<String, dynamic>>();
          final avg = summary['avg_score'];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text(avg == null ? '—' : '$avg%',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 8),
                    const Expanded(child: Text('average quality score')),
                    Text('${summary['datasets'] ?? 0} datasets',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              if (datasets.isEmpty)
                const PanelCard(
                    child: Text('No datasets yet. Add datasets and rules from the '
                        'web, then check real data against them.')),
              for (final ds in datasets) _DatasetCard(dataset: ds),
            ],
          );
        },
      ),
    );
  }
}

class _DatasetCard extends StatelessWidget {
  final Map<String, dynamic> dataset;
  const _DatasetCard({required this.dataset});

  @override
  Widget build(BuildContext context) {
    final rules = ((dataset['rules'] as List?) ?? []).cast<Map<String, dynamic>>();
    final latest = (dataset['latest'] as Map?)?.cast<String, dynamic>();
    final score = latest?['score'];
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
                      '${dataset['name']?.toString().isNotEmpty == true ? dataset['name'] : dataset['key']}',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                if (score != null)
                  Chip(
                    label: Text('$score%'),
                    backgroundColor: DataQualityScreen._scoreColor(score as int)
                        .withOpacity(0.15),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            const SizedBox(height: 4),
            if (rules.isEmpty)
              Text('No rules yet.',
                  style: Theme.of(context).textTheme.bodySmall)
            else
              for (final r in rules)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text('${r['field']} · ${r['check']}',
                            style: Theme.of(context).textTheme.bodyMedium),
                      ),
                      Text('${r['severity']}',
                          style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
            if (latest != null) ...[
              const Divider(height: 18),
              Text(
                  'Last check: ${latest['rows']} rows · ${latest['failing']} rule(s) failing',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}
