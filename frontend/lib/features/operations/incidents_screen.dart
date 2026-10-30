import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'operations_repository.dart';

/// Incident board (spec §20) on mobile: open incidents, timeline, and the lifecycle
/// actions. The app can note progress; only a person resolves — the backend enforces
/// that an incident stays open until explicitly resolved.
class IncidentsScreen extends ConsumerWidget {
  final int projectId;
  const IncidentsScreen({super.key, required this.projectId});

  Color _sevColor(BuildContext context, String sev) {
    final scheme = Theme.of(context).colorScheme;
    if (sev == 'critical' || sev == 'high') return scheme.error;
    if (sev == 'medium') return Colors.orange;
    return scheme.onSurfaceVariant;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final incidents = ref.watch(incidentsProvider(projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Incidents')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _open(context, ref),
        icon: const Icon(Icons.add_alert_outlined),
        label: const Text('Open'),
      ),
      body: incidents.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (payload) {
          final list = ((payload['incidents'] as List?) ?? [])
              .map((e) => Incident.fromJson(e as Map<String, dynamic>))
              .toList();
          final summary = (payload['summary'] as Map?)?.cast<String, dynamic>() ?? {};
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(incidentsProvider(projectId).future),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('${summary['open'] ?? 0} open · ${summary['total'] ?? 0} total',
                    style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 4),
                Text('A failed deploy opens an incident automatically. The AI can '
                    'help analyse, but only a person resolves one.',
                    style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 8),
                if (list.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Center(child: Text('No incidents.')),
                  ),
                for (final i in list)
                  Card(
                    child: ListTile(
                      leading: Icon(Icons.circle, size: 12, color: _sevColor(context, i.severity)),
                      title: Text(i.title),
                      subtitle: Text('${i.severity} · ${i.status} · ${i.source}'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => _detail(context, ref, i),
                    ),
                  ),
                const SizedBox(height: 72),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _open(BuildContext context, WidgetRef ref) async {
    final title = TextEditingController();
    final detail = TextEditingController();
    String severity = 'medium';
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
            bottom: MediaQuery.of(ctx).viewInsets.bottom, left: 16, right: 16, top: 16),
        child: StatefulBuilder(
          builder: (ctx, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Open an incident', style: Theme.of(ctx).textTheme.titleMedium),
              const SizedBox(height: 8),
              TextField(
                  controller: title,
                  decoration: const InputDecoration(labelText: 'Title')),
              DropdownButtonFormField<String>(
                value: severity,
                decoration: const InputDecoration(labelText: 'Severity'),
                items: const [
                  DropdownMenuItem(value: 'critical', child: Text('Critical')),
                  DropdownMenuItem(value: 'high', child: Text('High')),
                  DropdownMenuItem(value: 'medium', child: Text('Medium')),
                  DropdownMenuItem(value: 'low', child: Text('Low')),
                ],
                onChanged: (v) => setState(() => severity = v ?? 'medium'),
              ),
              TextField(
                  controller: detail,
                  maxLines: 2,
                  decoration: const InputDecoration(labelText: 'What was observed')),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                    onPressed: () => Navigator.pop(ctx, true),
                    child: const Text('Open incident')),
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
      ),
    );
    if (ok == true && title.text.trim().isNotEmpty) {
      if (!context.mounted) return;
      await _run(context, ref, () => ref
          .read(operationsRepositoryProvider)
          .openIncident(projectId,
              title: title.text.trim(), severity: severity, detail: detail.text.trim()));
    }
  }

  Future<void> _detail(BuildContext context, WidgetRef ref, Incident summary) async {
    // The list omits timelines; fetch the full incident for its timeline.
    Incident i = summary;
    try {
      i = await ref.read(operationsRepositoryProvider).incident(summary.id);
    } on ApiException catch (_) {
      // fall back to the summary (no timeline) rather than failing to open.
    }
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.6,
        maxChildSize: 0.9,
        builder: (ctx, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.all(16),
          children: [
            Text(i.title, style: Theme.of(ctx).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text('${i.severity} · ${i.status} · ${i.source}',
                style: Theme.of(ctx).textTheme.bodySmall),
            if (i.detail.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(i.detail),
            ],
            const Divider(height: 24),
            Text('Timeline', style: Theme.of(ctx).textTheme.titleSmall),
            for (final e in i.timeline)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.fiber_manual_record, size: 10),
                title: Text('${e['kind']}'
                    '${e['status'] != null && '${e['status']}'.isNotEmpty ? ' → ${e['status']}' : ''}'),
                subtitle: '${e['message'] ?? ''}'.isEmpty ? null : Text('${e['message']}'),
              ),
            const Divider(height: 24),
            Text('Update status', style: Theme.of(ctx).textTheme.titleSmall),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                for (final s in kIncidentStatuses)
                  ActionChip(
                    label: Text(s.$2),
                    onPressed: () async {
                      Navigator.pop(ctx);
                      await _run(context, ref, () => ref
                          .read(operationsRepositoryProvider)
                          .transition(i.id, s.$1));
                    },
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _run(
      BuildContext context, WidgetRef ref, Future<void> Function() action) async {
    try {
      await action();
      ref.invalidate(incidentsProvider(projectId));
      ref.invalidate(operationsProvider(projectId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
