import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'legal_repository.dart';

/// The Legal Center (spec §53): the agreements that govern the user's use of the
/// service, the exact versions they accepted, and a prompt for anything pending.
class LegalScreen extends ConsumerWidget {
  const LegalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(legalCenterProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Legal & Privacy')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final docs = (d['documents'] as List).cast<Map<String, dynamic>>();
          final accepted = (d['accepted'] as Map).cast<String, dynamic>();
          final pending = (d['pending'] as List).cast<Map<String, dynamic>>();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (pending.isNotEmpty)
                PanelCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Action needed',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 6),
                      Text('These documents changed since you last accepted them.',
                          style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 10),
                      for (final p in pending)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Row(
                            children: [
                              Expanded(
                                  child: Text('${p['title']} v${p['version']}')),
                              FilledButton.tonal(
                                onPressed: () =>
                                    _accept(context, ref, '${p['slug']}'),
                                child: const Text('I agree'),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
              if (pending.isNotEmpty) const SizedBox(height: 14),
              Text('Documents', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (docs.isEmpty)
                const PanelCard(child: Text('No legal documents have been published yet.'))
              else
                for (final doc in docs)
                  _DocTile(doc: doc, acceptance: accepted['${doc['slug']}']),
            ],
          );
        },
      ),
    );
  }

  Future<void> _accept(BuildContext context, WidgetRef ref, String slug) async {
    try {
      await ref.read(legalRepositoryProvider).accept(slug);
      ref.invalidate(legalCenterProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Your acceptance was recorded.')));
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _DocTile extends StatelessWidget {
  final Map<String, dynamic> doc;
  final Map<String, dynamic>? acceptance;
  const _DocTile({required this.doc, this.acceptance});

  @override
  Widget build(BuildContext context) {
    final requires = (doc['requires_acceptance'] ?? false) as bool;
    String status;
    if (acceptance != null) {
      status = 'Accepted v${acceptance!['version']}';
    } else if (requires) {
      status = 'Not yet accepted';
    } else {
      status = 'For reference';
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: PanelCard(
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${doc['title']}',
                      style: Theme.of(context).textTheme.titleSmall),
                  Text('v${doc['version']} · $status',
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            if (acceptance != null)
              const Icon(Icons.check_circle_outline, size: 18, color: Colors.green)
            else if (requires)
              const Icon(Icons.error_outline, size: 18, color: Color(0xFFC99A00)),
          ],
        ),
      ),
    );
  }
}
