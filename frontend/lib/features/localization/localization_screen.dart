import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'localization_repository.dart';

/// Localization (spec §17-18): the languages the app is offered in, with honest
/// per-language translation coverage.
class LocalizationScreen extends ConsumerWidget {
  final int projectId;
  const LocalizationScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(localizationProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Languages')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final locales =
              ((d['locales'] as List?) ?? []).cast<Map<String, dynamic>>();
          final coverage =
              ((d['coverage'] as List?) ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Row(
                  children: [
                    Text('${summary['locales'] ?? 0}',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(width: 6),
                    const Text('languages'),
                    const Spacer(),
                    Text('${summary['strings'] ?? 0} strings',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              _Section(
                title: 'Languages',
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final l in locales)
                      Chip(
                        label: Text('${l['name']}'
                            '${l['is_default'] == true ? ' · default' : ''}'
                            '${l['rtl'] == true ? ' · RTL' : ''}'),
                        visualDensity: VisualDensity.compact,
                      ),
                  ],
                ),
              ),
              if (coverage.isNotEmpty)
                _Section(
                  title: 'Translation coverage',
                  child: Column(
                    children: [
                      for (final c in coverage) _CoverageRow(cov: c),
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

class _CoverageRow extends StatelessWidget {
  final Map<String, dynamic> cov;
  const _CoverageRow({required this.cov});

  @override
  Widget build(BuildContext context) {
    final pct = (cov['percent'] ?? 0) as int;
    final color = pct == 100
        ? Colors.green
        : (pct >= 50 ? const Color(0xFFC99A00) : Colors.red);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text('${cov['name']} (${cov['code']})')),
              Text('${cov['translated']}/${cov['total']} · $pct%',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(99),
            child: LinearProgressIndicator(
                value: pct / 100,
                minHeight: 6,
                valueColor: AlwaysStoppedAnimation(color)),
          ),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  const _Section({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            child,
          ],
        ),
      ),
    );
  }
}
