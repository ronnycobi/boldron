import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'changes_repository.dart';

/// List + create change requests for a project (spec §12): describe a change in
/// plain language; the backend plans impact + estimate before any build.
class ChangesScreen extends ConsumerStatefulWidget {
  final int projectId;
  const ChangesScreen({super.key, required this.projectId});

  @override
  ConsumerState<ChangesScreen> createState() => _ChangesScreenState();
}

class _ChangesScreenState extends ConsumerState<ChangesScreen> {
  final _desc = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _desc.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    final text = _desc.text.trim();
    if (text.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    try {
      await ref.read(changesRepositoryProvider).create(widget.projectId, text);
      _desc.clear();
      ref.invalidate(changesProvider(widget.projectId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final changes = ref.watch(changesProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Request a change')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                TextField(
                  controller: _desc,
                  minLines: 2,
                  maxLines: 5,
                  decoration: const InputDecoration(
                    hintText:
                        'e.g. Add WhatsApp notifications · Fix the checkout bug',
                  ),
                ),
                const SizedBox(height: 10),
                FilledButton(
                  onPressed: _busy ? null : _create,
                  child: Text(_busy ? 'Planning…' : 'Plan this change'),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: changes.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text(e.toString())),
              data: (items) => items.isEmpty
                  ? const Center(child: Text('No changes yet.'))
                  : ListView.separated(
                      itemCount: items.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, i) {
                        final c = items[i];
                        return ListTile(
                          title: Text(c.description,
                              maxLines: 2, overflow: TextOverflow.ellipsis),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: StatusBadge(c.status),
                            ),
                          ),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => context.push('/changes/${c.id}'),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Change detail: plan, estimate and the approve → implement → rollback flow.
class ChangeDetailScreen extends ConsumerWidget {
  final int changeId;
  const ChangeDetailScreen({super.key, required this.changeId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final change = ref.watch(changeProvider(changeId));
    return Scaffold(
      appBar: AppBar(title: const Text('Change')),
      body: change.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (c) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(c.description, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(spacing: 8, children: [
              Chip(label: Text(c.statusDisplay)),
              if (c.risk.isNotEmpty) Chip(label: Text('Risk: ${c.risk}')),
              if (c.requiresApproval)
                Chip(label: Text(c.approved ? 'Approved' : 'Needs approval')),
            ]),
            if (c.impact != null && !c.impact!.isEmpty) ...[
              const SizedBox(height: 16),
              _ImpactCard(impact: c.impact!),
            ],
            if (c.plan['summary'] != null) ...[
              const SizedBox(height: 16),
              Text('Plan', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              Text('${c.plan['summary']}'),
            ],
            if (c.estimate.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Estimate', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              Text(_estimate(c.estimate)),
            ],
            const SizedBox(height: 24),
            _Actions(change: c),
          ],
        ),
      ),
    );
  }

  String _estimate(Map<String, dynamic> e) {
    final credits = e['credits'];
    if (credits is List && credits.length == 2) {
      return 'About ${credits[0]}–${credits[1]} AI credits.';
    }
    return e.toString();
  }
}

/// The §19 "proposed change" preview: what the change touches and the tests it
/// requires before shipping. Data comes from the shared backend impact engine —
/// the same one the web console renders.
class _ImpactCard extends StatelessWidget {
  final ChangeImpact impact;
  const _ImpactCard({required this.impact});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.surfaceVariant,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Proposed change',
                      style: Theme.of(context).textTheme.titleMedium),
                ),
                if (impact.riskLabel.isNotEmpty)
                  Chip(
                    label: Text('${impact.riskLabel} impact'),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            Text('${impact.testsRequired} test'
                '${impact.testsRequired == 1 ? '' : 's'} required before it ships',
                style: Theme.of(context).textTheme.bodySmall),
            if (impact.summary.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(impact.summary),
            ],
            if (impact.surfaces.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('This will touch',
                  style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 4),
              for (final s in impact.surfaces)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.check, size: 16, color: scheme.primary),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 96,
                        child: Text(s.name,
                            style: const TextStyle(fontWeight: FontWeight.w600)),
                      ),
                      Expanded(
                        child: Text(s.detail,
                            style: Theme.of(context).textTheme.bodySmall),
                      ),
                    ],
                  ),
                ),
            ],
            if (impact.requiredTests.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('Tests that must pass before it ships',
                  style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final t in impact.requiredTests)
                    Chip(
                      label: Text(t),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                ],
              ),
            ],
            if (impact.requiresApproval) ...[
              const SizedBox(height: 10),
              Text('This change needs your approval before it is implemented.',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

class _Actions extends ConsumerStatefulWidget {
  final ChangeRequest change;
  const _Actions({required this.change});

  @override
  ConsumerState<_Actions> createState() => _ActionsState();
}

class _ActionsState extends ConsumerState<_Actions> {
  bool _busy = false;

  Future<void> _run(Future<ChangeRequest> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
      ref.invalidate(changeProvider(widget.change.id));
      ref.invalidate(changesProvider(widget.change.project));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.change;
    final repo = ref.read(changesRepositoryProvider);
    final needsApproval = c.requiresApproval && !c.approved;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_busy) const Center(child: CircularProgressIndicator()),
        if (!_busy && needsApproval)
          FilledButton(
            onPressed: () => _run(() => repo.approve(c.id)),
            child: const Text('Approve'),
          ),
        if (!_busy && !needsApproval && c.status != 'done')
          FilledButton(
            onPressed: () => _run(() => repo.implement(c.id)),
            child: const Text('Build this change'),
          ),
        if (!_busy && c.canRollback) ...[
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: () => _run(() => repo.rollback(c.id)),
            child: const Text('Roll back'),
          ),
        ],
      ],
    );
  }
}
