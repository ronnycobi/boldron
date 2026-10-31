import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'compliance_repository.dart';

/// Compliance (spec §16): per-framework controls with honest status. Platform-
/// provided controls are auto-evidenced; the rest show as pending until attested.
class ComplianceScreen extends ConsumerWidget {
  final int projectId;
  const ComplianceScreen({super.key, required this.projectId});

  static Color _statusColor(String s) => switch (s) {
        'met' => Colors.green,
        'partial' => const Color(0xFFC99A00),
        'not_met' => Colors.red,
        _ => Colors.grey,
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(complianceProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Compliance')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final score = (d['score'] as Map?)?.cast<String, dynamic>() ?? {};
          final frameworks =
              ((score['frameworks'] as List?) ?? []).cast<Map<String, dynamic>>();
          final controls =
              ((d['controls'] as List?) ?? []).cast<Map<String, dynamic>>();
          // group controls by framework
          final byFw = <String, List<Map<String, dynamic>>>{};
          for (final c in controls) {
            byFw.putIfAbsent('${c['framework']}', () => []).add(c);
          }
          final labelByFw = {
            for (final f in frameworks) '${f['framework']}': f['label']
          };
          final overall = score['overall_percent'];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text(overall == null ? '—' : '$overall%',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 8),
                    const Expanded(child: Text('controls met overall')),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              for (final f in frameworks)
                _FrameworkTile(score: f),
              const SizedBox(height: 8),
              if (controls.isEmpty)
                const PanelCard(
                    child: Text('No frameworks tracked yet. Add one from the web '
                        'to see the controls your app needs.')),
              for (final entry in byFw.entries)
                _FrameworkControls(
                  label: '${labelByFw[entry.key] ?? entry.key}',
                  controls: entry.value,
                ),
            ],
          );
        },
      ),
    );
  }
}

class _FrameworkTile extends StatelessWidget {
  final Map<String, dynamic> score;
  const _FrameworkTile({required this.score});

  @override
  Widget build(BuildContext context) {
    final pct = score['percent'];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(child: Text('${score['label']}')),
          Text(
              pct == null
                  ? '—'
                  : '${score['met']}/${score['applicable']} · $pct%',
              style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _FrameworkControls extends StatelessWidget {
  final String label;
  final List<Map<String, dynamic>> controls;
  const _FrameworkControls({required this.label, required this.controls});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            for (final c in controls)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 3, right: 8),
                      child: Icon(Icons.circle,
                          size: 10,
                          color: ComplianceScreen._statusColor('${c['status']}')),
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${c['title']}'),
                          Text(
                            '${c['status_label']}'
                            '${c['auto'] == true ? ' · platform-provided' : ''}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
