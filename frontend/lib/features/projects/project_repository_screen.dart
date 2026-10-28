import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'projects_repository.dart';

/// The project's local git repository status (real). Connecting an external
/// remote needs an operator integration and is reported honestly as unavailable
/// until configured — never faked as connected.
class ProjectRepositoryScreen extends ConsumerWidget {
  final int projectId;
  const ProjectRepositoryScreen({super.key, required this.projectId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(projectRepositoryStatusProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Repository')),
      body: status.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) {
          final initialized = (d['initialized'] ?? false) as bool;
          final remote = (d['remote_configured'] ?? false) as bool;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Status'),
                trailing: Text(initialized ? 'Initialized' : 'Not built yet',
                    style: TextStyle(
                        color: initialized
                            ? const Color(0xFF4AD295)
                            : const Color(0xFFF5C454))),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Branch'),
                trailing: Text('${d['branch'] ?? '—'}',
                    style: const TextStyle(fontFamily: 'monospace')),
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Tracked files'),
                trailing: Text('${d['files'] ?? 0}'),
              ),
              const Divider(height: 28),
              Text('External remote',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 6),
              Text(
                remote
                    ? 'A git remote integration is configured on this deployment.'
                    : 'Pushing to GitHub/GitLab needs a git integration configured '
                        'by your operator. Until then the repository lives inside '
                        'the platform; export your code from Settings → Documents.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          );
        },
      ),
    );
  }
}
