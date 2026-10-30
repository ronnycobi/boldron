import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'quality_repository.dart';

/// Tests (spec §8) on mobile: the real test-run ledger, honest status, the tests the
/// latest change requires, and — when a run failed — the diagnosis + propose-a-fix.
class TestsScreen extends ConsumerWidget {
  final int projectId;
  const TestsScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tests = ref.watch(testsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Tests')),
      body: tests.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (t) {
          final latest = (t['latest'] as Map?)?.cast<String, dynamic>();
          final diagnosis = (t['diagnosis'] as Map?)?.cast<String, dynamic>();
          final required = ((t['required_tests'] as List?) ?? []).cast<dynamic>();
          final runs = ((t['runs'] as List?) ?? []).cast<dynamic>();
          final green = (t['green'] ?? false) as bool;
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(testsProvider(projectId).future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _StatusCard(
                  good: green,
                  title: green ? 'Tests are passing' : 'Not currently passing',
                  subtitle: latest != null
                      ? '${latest['summary']}'
                      : 'No test runs yet.',
                  note: green
                      ? null
                      : 'A production deploy is blocked until the suite passes.',
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: () => _run(context, ref,
                      () => ref.read(qualityRepositoryProvider).runTests(projectId)),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Run tests'),
                ),
                if (diagnosis != null) ...[
                  const SizedBox(height: 16),
                  _DiagnosisCard(
                    diagnosis: diagnosis,
                    onProposeFix: latest == null
                        ? null
                        : () => _proposeFix(context, ref, latest['id'] as int),
                  ),
                ],
                if (required.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text('Tests your latest change requires',
                      style: Theme.of(context).textTheme.titleSmall),
                  const SizedBox(height: 6),
                  Wrap(spacing: 6, runSpacing: 6, children: [
                    for (final r in required)
                      Chip(label: Text('$r'), visualDensity: VisualDensity.compact),
                  ]),
                ],
                const SizedBox(height: 16),
                Text('Run history', style: Theme.of(context).textTheme.titleSmall),
                for (final r in runs)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: _statusIcon(context, '${(r as Map)['status']}'),
                    title: Text('${r['summary']}'),
                    subtitle: Text('${r['trigger']} · ${r['created_at']}'),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _statusIcon(BuildContext context, String status) {
    final scheme = Theme.of(context).colorScheme;
    if (status == 'passed') return const Icon(Icons.check_circle, color: Colors.green);
    if (status == 'failed' || status == 'error') {
      return Icon(Icons.cancel, color: scheme.error);
    }
    return Icon(Icons.remove_circle_outline, color: scheme.onSurfaceVariant);
  }

  Future<void> _run(
      BuildContext context, WidgetRef ref, Future<void> Function() action) async {
    try {
      await action();
      ref.invalidate(testsProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _proposeFix(BuildContext context, WidgetRef ref, int runId) async {
    try {
      await ref.read(qualityRepositoryProvider).proposeFix(projectId, runId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('A fix was proposed as a change — review and approve it.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _StatusCard extends StatelessWidget {
  final bool good;
  final String title;
  final String subtitle;
  final String? note;
  const _StatusCard(
      {required this.good, required this.title, required this.subtitle, this.note});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(Icons.circle, size: 12,
                  color: good ? Colors.green : Theme.of(context).colorScheme.onSurfaceVariant),
              const SizedBox(width: 8),
              Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
            ]),
            const SizedBox(height: 4),
            Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            if (note != null) ...[
              const SizedBox(height: 6),
              Text(note!, style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

class _DiagnosisCard extends StatelessWidget {
  final Map<String, dynamic> diagnosis;
  final VoidCallback? onProposeFix;
  const _DiagnosisCard({required this.diagnosis, this.onProposeFix});

  @override
  Widget build(BuildContext context) {
    final failing = ((diagnosis['failing_tests'] as List?) ?? []).cast<dynamic>();
    return Card(
      color: Theme.of(context).colorScheme.errorContainer.withOpacity(.4),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('What went wrong', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text('Likely cause: ${diagnosis['root_cause']}'),
            if (diagnosis['suggested_fix'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Suggested: ${diagnosis['suggested_fix']}'),
              ),
            if (failing.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Failing: ${failing.join(', ')}',
                    style: Theme.of(context).textTheme.bodySmall),
              ),
            if (diagnosis['location'] != null &&
                '${diagnosis['location']}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Around ${diagnosis['location']}',
                    style: Theme.of(context).textTheme.bodySmall),
              ),
            if (onProposeFix != null) ...[
              const SizedBox(height: 10),
              FilledButton.tonal(
                onPressed: onProposeFix,
                child: const Text('Propose a fix'),
              ),
              Text('A fix is a reviewed change — implemented and re-tested before '
                  'anything is called fixed.',
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}
