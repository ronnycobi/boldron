import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'acceptance_repository.dart';

/// Acceptance criteria (spec §3): the testable conditions each requirement must
/// meet, with an honest status. A criterion is marked met only when a person
/// verifies it — the app never claims acceptance it can't evidence.
class AcceptanceScreen extends ConsumerWidget {
  final int projectId;
  const AcceptanceScreen({super.key, required this.projectId});

  static const _statuses = {
    'pending': 'Pending',
    'met': 'Met',
    'failed': 'Not met',
    'waived': 'Waived',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(acceptanceProvider(projectId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Acceptance criteria'),
        actions: [
          IconButton(
            tooltip: 'Import from requirements',
            icon: const Icon(Icons.download_outlined),
            onPressed: () => _import(context, ref),
          ),
        ],
      ),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final summary =
              (d['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          final criteria =
              ((d['criteria'] as List?) ?? []).cast<Map<String, dynamic>>();
          // Group by requirement title (null/empty -> "Other criteria").
          final groups = <String, List<Map<String, dynamic>>>{};
          for (final c in criteria) {
            final title = (c['requirement_title'] as String?)?.trim();
            groups.putIfAbsent(
                title == null || title.isEmpty ? 'Other criteria' : title,
                () => []).add(c);
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _SummaryCard(summary: summary),
              const SizedBox(height: 14),
              if (criteria.isEmpty)
                const PanelCard(
                  child: Text(
                      'No acceptance criteria yet. Use the import button to pull '
                      'them from your requirements.'),
                ),
              for (final entry in groups.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: PanelCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(entry.key,
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 4),
                        for (final c in entry.value)
                          _CriterionRow(
                            criterion: c,
                            onVerify: (status) =>
                                _verify(context, ref, c['id'] as int, status),
                          ),
                      ],
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _import(BuildContext context, WidgetRef ref) async {
    try {
      final res =
          await ref.read(acceptanceRepositoryProvider).importFromRequirements(projectId);
      ref.invalidate(acceptanceProvider(projectId));
      if (context.mounted) {
        final n = res['imported'] ?? 0;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(n == 0
                ? 'No new criteria to import.'
                : 'Imported $n criteria from requirements.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _verify(
      BuildContext context, WidgetRef ref, int id, String status) async {
    try {
      await ref.read(acceptanceRepositoryProvider).verify(id, status);
      ref.invalidate(acceptanceProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _SummaryCard extends StatelessWidget {
  final Map<String, dynamic> summary;
  const _SummaryCard({required this.summary});

  @override
  Widget build(BuildContext context) {
    final total = (summary['total'] ?? 0) as int;
    final met = (summary['met'] ?? 0) as int;
    final pct = summary['met_pct'];
    final accepted = (summary['accepted'] ?? false) as bool;
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('$met', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(width: 6),
              Text('of $total met',
                  style: Theme.of(context).textTheme.bodyMedium),
              const Spacer(),
              Chip(
                label: Text(accepted ? 'Accepted' : 'Not yet met'),
                backgroundColor:
                    accepted ? Colors.green.withOpacity(0.15) : null,
              ),
            ],
          ),
          if (total > 0) ...[
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                  value: (pct == null ? 0 : (pct as int)) / 100, minHeight: 8),
            ),
          ],
          const SizedBox(height: 8),
          Text(_detail(summary),
              style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }

  String _detail(Map<String, dynamic> s) {
    final parts = <String>[];
    if ((s['pending'] ?? 0) as int > 0) parts.add('${s['pending']} pending');
    if ((s['failed'] ?? 0) as int > 0) parts.add('${s['failed']} not met');
    if ((s['waived'] ?? 0) as int > 0) parts.add('${s['waived']} waived');
    return parts.isEmpty ? 'All criteria resolved.' : parts.join(' · ');
  }
}

class _CriterionRow extends StatelessWidget {
  final Map<String, dynamic> criterion;
  final ValueChanged<String> onVerify;
  const _CriterionRow({required this.criterion, required this.onVerify});

  Color? _color(String status) => switch (status) {
        'met' => Colors.green,
        'failed' => Colors.red,
        'waived' => Colors.grey,
        _ => Colors.orange,
      };

  @override
  Widget build(BuildContext context) {
    final status = '${criterion['status']}';
    final verifiedBy = criterion['verified_by'];
    return Container(
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: Theme.of(context).dividerColor)),
      ),
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 3, right: 8),
            child: Icon(Icons.circle, size: 10, color: _color(status)),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${criterion['statement']}'),
                Text(
                  '${criterion['status_label']}'
                  '${verifiedBy != null ? ' · verified by $verifiedBy' : ''}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          PopupMenuButton<String>(
            tooltip: 'Set status',
            icon: const Icon(Icons.more_vert, size: 18),
            onSelected: onVerify,
            itemBuilder: (_) => [
              for (final e in AcceptanceScreen._statuses.entries)
                PopupMenuItem(value: e.key, child: Text(e.value)),
            ],
          ),
        ],
      ),
    );
  }
}
