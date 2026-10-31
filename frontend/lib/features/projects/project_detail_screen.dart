import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/brand.dart';
import 'project_models.dart';
import 'projects_repository.dart';

/// One manageable area linked from the project hub.
typedef _Area = ({IconData icon, String label, String path});

/// Areas shown on the hub. Add to this list as each area screen ships (its
/// route lives in the router under /projects/:id/<path>).
const List<_Area> _areas = [
  (icon: Icons.tune, label: 'Request a change', path: 'changes'),
  (icon: Icons.lightbulb_outline, label: 'Explain', path: 'explain'),
  (icon: Icons.favorite_outline, label: 'Health', path: 'health'),
  (icon: Icons.flag_outlined, label: 'Feature flags', path: 'flags'),
  (icon: Icons.translate_outlined, label: 'Languages', path: 'localization'),
  (icon: Icons.science_outlined, label: 'Experiments', path: 'experiments'),
  (icon: Icons.hub_outlined, label: 'App graph', path: 'graph'),
  (icon: Icons.checklist_outlined, label: 'Acceptance', path: 'acceptance'),
  (icon: Icons.gavel_outlined, label: 'Business rules', path: 'rules'),
  (icon: Icons.bolt_outlined, label: 'Automations', path: 'automations'),
  (icon: Icons.policy_outlined, label: 'Policies', path: 'policies'),
  (icon: Icons.forum_outlined, label: 'Comments', path: 'comments'),
  (icon: Icons.monitor_heart_outlined, label: 'Operations', path: 'operations'),
  (icon: Icons.verified_outlined, label: 'Tests', path: 'tests'),
  (icon: Icons.shield_outlined, label: 'Security', path: 'security'),
  (icon: Icons.devices_outlined, label: 'Compatibility', path: 'compatibility'),
  (icon: Icons.rocket_launch_outlined, label: 'Deployments', path: 'deployments'),
  (icon: Icons.public, label: 'Website', path: 'website'),
  (icon: Icons.storefront_outlined, label: 'Store', path: 'commerce'),
  (icon: Icons.phone_iphone, label: 'Mobile releases', path: 'releases'),
  (icon: Icons.settings_backup_restore, label: 'Backups', path: 'backups'),
  (icon: Icons.key_outlined, label: 'Environment', path: 'environment'),
  (icon: Icons.folder_outlined, label: 'Files', path: 'files'),
  (icon: Icons.auto_awesome_outlined, label: 'AI', path: 'ai'),
  (icon: Icons.source_outlined, label: 'Repository', path: 'repository'),
];

/// The per-project hub: live build status while it builds, plus entry points to
/// the project's areas (changes, deployments, website, commerce, releases).
class ProjectDetailScreen extends ConsumerStatefulWidget {
  final int projectId;
  const ProjectDetailScreen({super.key, required this.projectId});

  @override
  ConsumerState<ProjectDetailScreen> createState() =>
      _ProjectDetailScreenState();
}

class _ProjectDetailScreenState extends ConsumerState<ProjectDetailScreen> {
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    // Poll build status every 4s; it stops polling once the build settles.
    _poll = Timer.periodic(const Duration(seconds: 4), (_) {
      final status = ref.read(buildStatusProvider(widget.projectId));
      final building = status.valueOrNull?.state == 'Building';
      if (building) {
        ref.invalidate(buildStatusProvider(widget.projectId));
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectProvider(widget.projectId));
    final status = ref.watch(buildStatusProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(
        title: Text(project.valueOrNull?.name ?? 'Project'),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(projectProvider(widget.projectId));
          ref.invalidate(buildStatusProvider(widget.projectId));
          await ref.read(projectProvider(widget.projectId).future);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            project.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Text(e.toString()),
              data: (p) => _Header(project: p),
            ),
            const SizedBox(height: 12),
            status.when(
              loading: () => const Card(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: CircularProgressIndicator()),
                ),
              ),
              error: (e, _) => const SizedBox.shrink(),
              data: (s) => _BuildStatusCard(status: s),
            ),
            const SizedBox(height: 16),
            Text('Manage', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final area in _areas)
              _AreaTile(
                icon: area.icon,
                label: area.label,
                onTap: () => context
                    .push('/projects/${widget.projectId}/${area.path}'),
              ),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final Project project;
  const _Header({required this.project});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(project.name,
                  style: Theme.of(context).textTheme.headlineSmall),
            ),
            StatusBadge(project.status),
          ],
        ),
        if (project.description.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(project.description),
        ],
      ],
    );
  }
}

class _BuildStatusCard extends StatelessWidget {
  final BuildStatus status;
  const _BuildStatusCard({required this.status});

  @override
  Widget build(BuildContext context) {
    final building = status.state == 'Building';
    return PanelCard(
      child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Build', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                Text('${status.progress}%'),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: status.progress / 100),
            if (status.demoMode) ...[
              const SizedBox(height: 12),
              _DemoModeNote(),
            ],
            const SizedBox(height: 12),
            for (final step in status.steps)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: _StepIcon(step.status),
                title: Text(_friendly(step.key)),
                subtitle: step.detail.isEmpty ? null : Text(step.detail),
              ),
            if (building)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text('Building… this refreshes automatically.'),
              ),
          ],
        ),
    );
  }

  static String _friendly(String key) {
    const names = {
      'requirements': 'Understanding your requirements',
      'architect': 'Designing the structure',
      'database': 'Setting up data',
      'backend': 'Building the core',
      'frontend': 'Designing the screens',
      'testing': 'Testing your application',
      'code_review': 'Reviewing the code',
      'security': 'Checking security',
    };
    return names[key] ?? key;
  }
}

class _StepIcon extends StatelessWidget {
  final String status;
  const _StepIcon(this.status);

  @override
  Widget build(BuildContext context) {
    switch (status) {
      case 'completed':
        return const Icon(Icons.check_circle, color: Colors.green, size: 20);
      case 'failed':
        return Icon(Icons.error,
            color: Theme.of(context).colorScheme.error, size: 20);
      case 'running':
        return const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
      default:
        return Icon(Icons.radio_button_unchecked,
            color: Theme.of(context).colorScheme.outline, size: 20);
    }
  }
}

class _DemoModeNote extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.tertiaryContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        'This build ran in offline demo mode — it produced placeholder output, '
        'not real code. Rebuild once a model is connected.',
        style: TextStyle(color: scheme.onTertiaryContainer, fontSize: 12.5),
      ),
    );
  }
}

class _AreaTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _AreaTile({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: PanelCard(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          onTap: onTap,
          child: Row(
            children: [
              Icon(icon, size: 20),
              const SizedBox(width: 14),
              Expanded(child: Text(label)),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      );
}
