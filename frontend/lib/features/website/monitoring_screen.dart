import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'website_repository.dart';

/// Website health (spec §25): uptime summary + the latest serve probe, with a
/// "Check now" action. Honest scope — this is the snapshot the platform serves,
/// not remote server metrics it can't see.
class MonitoringScreen extends ConsumerStatefulWidget {
  final int projectId;
  const MonitoringScreen({super.key, required this.projectId});

  @override
  ConsumerState<MonitoringScreen> createState() => _MonitoringScreenState();
}

class _MonitoringScreenState extends ConsumerState<MonitoringScreen> {
  bool _busy = false;

  Future<void> _check() async {
    setState(() => _busy = true);
    try {
      await ref.read(websiteRepositoryProvider).runCheck(widget.projectId);
      ref.invalidate(monitoringProvider(widget.projectId));
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
    final mon = ref.watch(monitoringProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Monitoring')),
      body: mon.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (m) {
          final uptime = (m['uptime'] as Map?) ?? {};
          final latest = m['latest'] as Map?;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('Uptime',
                            style: Theme.of(context).textTheme.titleMedium),
                        const Spacer(),
                        Text('${uptime['uptime_pct'] ?? uptime['percent'] ?? '—'}%',
                            style: Theme.of(context).textTheme.titleMedium),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${uptime['checks'] ?? uptime['total'] ?? 0} checks · '
                      '${uptime['up'] ?? 0} up',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('Latest check',
                            style: Theme.of(context).textTheme.titleMedium),
                        const Spacer(),
                        if (latest != null) StatusBadge('${latest['status']}'),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(latest == null
                        ? 'No checks yet.'
                        : '${latest['detail'] ?? ''}'
                            '${latest['response_ms'] != null ? ' · ${latest['response_ms']} ms' : ''}'),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              GradientButton(
                onPressed: _busy ? null : _check,
                child: Text(_busy ? 'Checking…' : 'Check now'),
              ),
            ],
          );
        },
      ),
    );
  }
}
