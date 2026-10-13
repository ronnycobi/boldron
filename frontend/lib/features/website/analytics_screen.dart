import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'website_repository.dart';

/// Visitor analytics for the published site (spec §26) — real, privacy-
/// preserving data: visitors, sessions, conversion, top pages and sources.
class AnalyticsScreen extends ConsumerWidget {
  final int projectId;
  const AnalyticsScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final a = ref.watch(analyticsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Analytics')),
      body: a.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final topPages = (d['top_pages'] as List?) ?? [];
          final sources = (d['sources'] as List?) ?? [];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Last ${d['days'] ?? 30} days',
                  style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 10),
              Row(
                children: [
                  _Stat(label: 'Visitors', value: '${d['visitors'] ?? 0}'),
                  const SizedBox(width: 10),
                  _Stat(label: 'Page views', value: '${d['pageviews'] ?? 0}'),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  _Stat(label: 'Leads', value: '${d['leads'] ?? 0}'),
                  const SizedBox(width: 10),
                  _Stat(label: 'Conversion', value: '${d['conversion'] ?? 0}%'),
                ],
              ),
              const SizedBox(height: 20),
              Text('Top pages', style: Theme.of(context).textTheme.titleMedium),
              if (topPages.isEmpty) const Text('No traffic yet.'),
              for (final p in topPages)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  title: Text('${(p as Map)['path']}'),
                  trailing: Text('${p['n']}'),
                ),
              if (sources.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('Traffic sources',
                    style: Theme.of(context).textTheme.titleMedium),
                for (final s in sources)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text('${(s as Map)['referrer_host']}'),
                    trailing: Text('${s['n']}'),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  const _Stat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Expanded(
        child: PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 4),
              Text(value,
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w700)),
            ],
          ),
        ),
      );
}
