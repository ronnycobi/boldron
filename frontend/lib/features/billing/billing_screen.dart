import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'billing_repository.dart';

/// Plan, credits, usage and upgrade (spec §21/§22). Honest — it shows real
/// credit/usage data; "upgrade" opens a request (no live payment provider).
class BillingScreen extends ConsumerWidget {
  final int orgId;
  const BillingScreen({super.key, required this.orgId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final billing = ref.watch(billingProvider(orgId));
    final usage = ref.watch(usageSummaryProvider(orgId));
    return Scaffold(
      appBar: AppBar(title: const Text('Billing & usage')),
      body: billing.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (b) {
          final remaining = (b['remaining_pct'] ?? 0) as int;
          final upgrades = (b['upgrades'] as List?) ?? [];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('${b['label'] ?? b['plan']}',
                            style: Theme.of(context).textTheme.titleLarge),
                        const Spacer(),
                        Text('${b['price'] ?? ''}'),
                      ],
                    ),
                    const SizedBox(height: 12),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(99),
                      child: LinearProgressIndicator(
                          value: remaining / 100, minHeight: 9),
                    ),
                    const SizedBox(height: 6),
                    Text(
                        'Credits: ${b['balance']} left of ${b['allowance']} ($remaining%)'),
                    const SizedBox(height: 4),
                    Text('This month: ${b['month_credits']} credits used'),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              usage.when(
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
                data: (u) {
                  final byModel = (u['by_model'] as List?) ?? [];
                  if (byModel.isEmpty) return const SizedBox.shrink();
                  return PanelCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Usage this month',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        for (final m in byModel)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 2),
                            child: Row(
                              children: [
                                Expanded(child: Text('${(m as Map)['model']}')),
                                Text('${m['credits']} cr'),
                              ],
                            ),
                          ),
                      ],
                    ),
                  );
                },
              ),
              const SizedBox(height: 16),
              if (upgrades.isNotEmpty) ...[
                Text('Upgrade', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                for (final u in upgrades)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: PanelCard(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      child: Row(
                        children: [
                          Expanded(
                              child: Text(
                                  '${(u as Map)['label']} · ${u['price']}')),
                          FilledButton.tonal(
                            onPressed: (b['can_manage'] ?? false) as bool
                                ? () => _requestUpgrade(
                                    context, ref, '${u['plan']}', '${u['label']}')
                                : null,
                            child: const Text('Request'),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<void> _requestUpgrade(
      BuildContext context, WidgetRef ref, String plan, String label) async {
    try {
      final ticket =
          await ref.read(billingRepositoryProvider).requestUpgrade(orgId, plan);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(
                  'Upgrade request sent${ticket.isNotEmpty ? ' ($ticket)' : ''} — our team will follow up.')),
        );
      }
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
