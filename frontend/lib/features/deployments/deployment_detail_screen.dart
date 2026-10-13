import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'deployments_repository.dart';

/// One deployment: live status + customer-safe log, with approve/run when the
/// deployment is waiting (spec §15).
class DeploymentDetailScreen extends ConsumerStatefulWidget {
  final int deploymentId;
  const DeploymentDetailScreen({super.key, required this.deploymentId});

  @override
  ConsumerState<DeploymentDetailScreen> createState() =>
      _DeploymentDetailScreenState();
}

class _DeploymentDetailScreenState
    extends ConsumerState<DeploymentDetailScreen> {
  Timer? _poll;
  bool _busy = false;

  static const _active = {'pending', 'waiting_for_approval', 'deploying'};

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 3), (_) {
      final d = ref.read(deploymentProvider(widget.deploymentId)).valueOrNull;
      if (d != null && _active.contains(d.status)) {
        ref.invalidate(deploymentProvider(widget.deploymentId));
      }
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _run(Future<Deployment> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
      ref.invalidate(deploymentProvider(widget.deploymentId));
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
    final deployment = ref.watch(deploymentProvider(widget.deploymentId));
    final repo = ref.read(deploymentsRepositoryProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Deployment')),
      body: deployment.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (d) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Row(
              children: [
                Text(d.environment,
                    style: Theme.of(context).textTheme.titleLarge),
                const Spacer(),
                StatusBadge(d.status),
              ],
            ),
            if (d.url.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(d.url),
            ],
            const SizedBox(height: 16),
            if (!_busy && d.status == 'waiting_for_approval')
              FilledButton(
                onPressed: () => _run(() => repo.approve(d.id)),
                child: const Text('Approve'),
              ),
            if (!_busy && (d.status == 'pending' || d.status == 'waiting_for_approval'))
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: OutlinedButton(
                  onPressed: () => _run(() => repo.run(d.id)),
                  child: const Text('Run deployment'),
                ),
              ),
            const SizedBox(height: 16),
            Text('Log', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceVariant,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                d.log.isEmpty ? 'No log output yet.' : d.log,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12.5),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
