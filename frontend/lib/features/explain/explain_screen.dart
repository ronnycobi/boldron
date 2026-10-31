import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import 'explain_repository.dart';

/// Explain my application (spec §29): a plain-language account of what the app
/// is, what it does, what it's made of and what state it's in.
class ExplainScreen extends ConsumerWidget {
  final int projectId;
  const ExplainScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(explainProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('What is this app?')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final does = ((d['does'] as List?) ?? []).cast<String>();
          final coming = ((d['coming'] as List?) ?? []).cast<String>();
          final parts = ((d['parts'] as List?) ?? []).cast<Map<String, dynamic>>();
          final platforms = ((d['platforms'] as List?) ?? []).cast<String>();
          final requirements =
              ((d['requirements'] as List?) ?? []).cast<String>();
          final rules = ((d['rules'] as List?) ?? []).cast<String>();
          final health = (d['health'] as Map?)?.cast<String, dynamic>() ?? {};
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${d['summary']}',
                        style: Theme.of(context).textTheme.titleMedium),
                    if ('${d['description'] ?? ''}'.trim().isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text('${d['description']}',
                          style: Theme.of(context).textTheme.bodyMedium),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 14),
              _Section(
                title: 'What it does',
                child: does.isEmpty && coming.isEmpty
                    ? const Text('Still being set up.')
                    : Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          for (final f in does) Chip(label: Text(f)),
                          for (final f in coming)
                            Chip(
                              label: Text('$f (coming)'),
                              visualDensity: VisualDensity.compact,
                            ),
                        ],
                      ),
              ),
              _Section(
                title: "What it's made of",
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final p in parts)
                      Text('${p['count']}  ${p['label']}'),
                    if (platforms.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text('Runs on: ${platforms.join(', ')}',
                          style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ],
                ),
              ),
              _Section(
                title: 'What state it\'s in',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                            health['score'] == null
                                ? '—'
                                : '${health['score']}/100',
                            style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(width: 8),
                        Chip(
                            label: Text('${health['band']}'),
                            visualDensity: VisualDensity.compact),
                      ],
                    ),
                    Text('${health['headline'] ?? ''}',
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
              if (requirements.isNotEmpty)
                _Section(
                  title: 'What it needs to do',
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [for (final r in requirements) Chip(label: Text(r))],
                  ),
                ),
              if (rules.isNotEmpty)
                _Section(
                  title: 'Rules it follows',
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [for (final r in rules) Chip(label: Text(r))],
                  ),
                ),
            ],
          );
        },
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
