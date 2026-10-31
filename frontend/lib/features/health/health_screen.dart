import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'health_repository.dart';

/// Project Health (spec §30): one composed, honest signal with the per-pillar
/// breakdown it was derived from. A pillar with no evidence shows as unknown.
class HealthScreen extends ConsumerWidget {
  final int projectId;
  const HealthScreen({super.key, required this.projectId});

  static Color _bandColor(String band) => switch (band) {
        'good' => Colors.green,
        'fair' => const Color(0xFFC99A00),
        'poor' => Colors.red,
        _ => Colors.grey,
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(healthProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Project health')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (h) {
          final pillars =
              ((h['pillars'] as List?) ?? []).cast<Map<String, dynamic>>();
          final score = h['score'];
          final band = '${h['band']}';
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Column(
                      children: [
                        Text(score == null ? '—' : '$score',
                            style: Theme.of(context)
                                .textTheme
                                .displaySmall
                                ?.copyWith(fontWeight: FontWeight.bold)),
                        Chip(
                          label: Text(band),
                          backgroundColor: _bandColor(band).withOpacity(0.15),
                          visualDensity: VisualDensity.compact,
                        ),
                      ],
                    ),
                    const SizedBox(width: 18),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${h['headline']}',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 6),
                          Text(
                              'Based on ${h['measured']} measured signal(s) of '
                              '${pillars.length}.',
                              style: Theme.of(context).textTheme.bodySmall),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              for (final p in pillars) _PillarCard(pillar: p),
            ],
          );
        },
      ),
    );
  }
}

class _PillarCard extends StatelessWidget {
  final Map<String, dynamic> pillar;
  const _PillarCard({required this.pillar});

  @override
  Widget build(BuildContext context) {
    final status = '${pillar['status']}';
    final score = pillar['score'];
    final color = HealthScreen._bandColor(
        status == 'good' ? 'good' : (status == 'fair' ? 'fair'
            : status == 'poor' ? 'poor' : 'unknown'));
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('${pillar['label']}',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                Chip(
                  label: Text(status),
                  backgroundColor: color.withOpacity(0.15),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text('${pillar['detail']}',
                style: Theme.of(context).textTheme.bodySmall),
            if (score != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(99),
                child: LinearProgressIndicator(
                    value: (score as int) / 100,
                    minHeight: 6,
                    valueColor: AlwaysStoppedAnimation(color)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
