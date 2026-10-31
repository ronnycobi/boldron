import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'rules_repository.dart';

/// Business rules (spec §12-13): the policies the app runs on, with an honest
/// enforced/documented split and a draft→active→retired lifecycle. A person
/// changes status; the app never invents enforcement.
class RulesScreen extends ConsumerWidget {
  final int projectId;
  const RulesScreen({super.key, required this.projectId});

  static const _statuses = {
    'draft': 'Draft',
    'active': 'Active',
    'retired': 'Retired',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(rulesProvider(projectId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Business rules'),
        actions: [
          IconButton(
            tooltip: 'Import from project memory',
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
          final rules =
              ((d['rules'] as List?) ?? []).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _SummaryCard(summary: summary),
              const SizedBox(height: 14),
              if (rules.isEmpty)
                const PanelCard(
                  child: Text(
                      'No business rules yet. Use the import button to pull the '
                      'policies recorded in project memory.'),
                ),
              for (final r in rules)
                _RuleCard(
                  rule: r,
                  onStatus: (s) => _setStatus(context, ref, r['id'] as int, s),
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
          await ref.read(rulesRepositoryProvider).importFromContext(projectId);
      ref.invalidate(rulesProvider(projectId));
      if (context.mounted) {
        final n = res['imported'] ?? 0;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(n == 0
                ? 'No new rules to import.'
                : 'Imported $n rule(s) from project memory.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _setStatus(
      BuildContext context, WidgetRef ref, int id, String status) async {
    try {
      await ref.read(rulesRepositoryProvider).setStatus(id, status);
      ref.invalidate(rulesProvider(projectId));
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
    final active = (summary['active'] ?? 0) as int;
    final enforced = (summary['enforced'] ?? 0) as int;
    final documented = (summary['documented'] ?? 0) as int;
    return PanelCard(
      child: Row(
        children: [
          Text('$active', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(width: 6),
          const Text('active'),
          const Spacer(),
          Chip(label: Text('$enforced enforced')),
          if (documented > 0) ...[
            const SizedBox(width: 6),
            Text('$documented documented',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ],
      ),
    );
  }
}

class _RuleCard extends StatelessWidget {
  final Map<String, dynamic> rule;
  final ValueChanged<String> onStatus;
  const _RuleCard({required this.rule, required this.onStatus});

  @override
  Widget build(BuildContext context) {
    final status = '${rule['status']}';
    final enforceable = (rule['enforceable'] ?? false) as bool;
    final desc = (rule['description'] as String?)?.trim() ?? '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('${rule['name']}',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                PopupMenuButton<String>(
                  tooltip: 'Set status',
                  icon: const Icon(Icons.more_vert, size: 18),
                  onSelected: onStatus,
                  itemBuilder: (_) => [
                    for (final e in RulesScreen._statuses.entries)
                      PopupMenuItem(value: e.key, child: Text(e.value)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 4),
            Wrap(
              spacing: 6,
              children: [
                Chip(
                  label: Text('${rule['status_label']}'),
                  visualDensity: VisualDensity.compact,
                ),
                Chip(
                  label: Text(enforceable ? 'Enforced' : 'Documented'),
                  visualDensity: VisualDensity.compact,
                ),
                Chip(
                  label: Text('${rule['category_label']}'),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
            if (desc.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(desc, style: Theme.of(context).textTheme.bodyMedium),
            ],
            if (!enforceable && status == 'active') ...[
              const SizedBox(height: 6),
              Text('Policy only — not automatically applied.',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}
