import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import 'deployments_repository.dart';

/// Environments and their latest deployment (spec §15). A manager can deploy to
/// an environment; production deploys follow the backend's approval policy.
class DeploymentsScreen extends ConsumerStatefulWidget {
  final int projectId;
  const DeploymentsScreen({super.key, required this.projectId});

  @override
  ConsumerState<DeploymentsScreen> createState() => _DeploymentsScreenState();
}

class _DeploymentsScreenState extends ConsumerState<DeploymentsScreen> {
  String? _deploying;

  Future<void> _deploy(String environment) async {
    setState(() => _deploying = environment);
    try {
      await ref
          .read(deploymentsRepositoryProvider)
          .deploy(widget.projectId, environment);
      ref.invalidate(environmentsProvider(widget.projectId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _deploying = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final envs = ref.watch(environmentsProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Deployments')),
      body: RefreshIndicator(
        onRefresh: () async =>
            ref.refresh(environmentsProvider(widget.projectId).future),
        child: envs.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(e.toString())),
          ]),
          data: (items) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              for (final env in items) _EnvCard(
                env: env,
                deploying: _deploying == env.environment,
                onDeploy: () => _deploy(env.environment),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EnvCard extends StatelessWidget {
  final EnvironmentSummary env;
  final bool deploying;
  final VoidCallback onDeploy;
  const _EnvCard({
    required this.env,
    required this.deploying,
    required this.onDeploy,
  });

  @override
  Widget build(BuildContext context) {
    final latest = env.latest;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(env.label,
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                if (latest != null)
                  Chip(
                    label: Text(latest.status),
                    visualDensity: VisualDensity.compact,
                  ),
              ],
            ),
            const SizedBox(height: 4),
            InkWell(
              onTap: latest == null
                  ? null
                  : () => context.push('/deployments/${latest.id}'),
              child: Text(
                latest == null
                    ? 'Never deployed'
                    : (latest.url.isNotEmpty
                        ? latest.url
                        : 'Last: ${latest.status} — view log'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.tonal(
                onPressed: deploying ? null : onDeploy,
                child: Text(deploying
                    ? 'Deploying…'
                    : (latest == null ? 'Deploy' : 'Redeploy')),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
