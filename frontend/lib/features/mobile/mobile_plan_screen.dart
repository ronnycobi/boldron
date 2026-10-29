import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'mobile_repository.dart';

/// Plan a mobile app from a plain-language brief (spec §5/§48). Shows the honest
/// plan — capabilities (built-in vs needs-connection), device permissions, and
/// target platforms — before any build. Nothing here signs or submits anything.
class MobilePlanScreen extends ConsumerStatefulWidget {
  final String initialBrief;
  const MobilePlanScreen({super.key, this.initialBrief = ''});

  @override
  ConsumerState<MobilePlanScreen> createState() => _MobilePlanScreenState();
}

class _MobilePlanScreenState extends ConsumerState<MobilePlanScreen> {
  late final TextEditingController _brief =
      TextEditingController(text: widget.initialBrief);
  final Set<String> _platforms = {'ios', 'android', 'huawei'};
  MobilePlan? _plan;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _brief.dispose();
    super.dispose();
  }

  Future<void> _runPlan() async {
    final brief = _brief.text.trim();
    if (brief.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await ref
          .read(mobileRepositoryProvider)
          .plan(brief, platforms: _platforms.toList());
      if (!mounted) return;
      setState(() => _plan = result);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Plan a mobile app')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Describe your app. We work out the screens, capabilities, device '
              'permissions and platforms — and show honestly what is built-in '
              'versus what needs your developer accounts connected.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _brief,
              minLines: 3,
              maxLines: 6,
              decoration: const InputDecoration(
                labelText: 'What should the app do?',
                hintText:
                    'e.g. Field app: log jobs, take photos, capture GPS, work offline…',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                for (final p in kMobilePlatforms)
                  FilterChip(
                    label: Text(p.name),
                    selected: _platforms.contains(p.id),
                    onSelected: (on) => setState(() =>
                        on ? _platforms.add(p.id) : _platforms.remove(p.id)),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _busy || _platforms.isEmpty ? null : _runPlan,
              icon: _busy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.auto_awesome),
              label: const Text('Plan it'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            if (_plan != null) ...[
              const SizedBox(height: 20),
              _PlanView(plan: _plan!),
            ],
          ],
        ),
      ),
    );
  }
}

class _PlanView extends StatelessWidget {
  final MobilePlan plan;
  const _PlanView({required this.plan});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Your mobile app plan',
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        Text(
          '${plan.generatedCount} built-in · ${plan.gatedCount} needs connection · '
          '${plan.plannedCount} coming',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final p in plan.platforms)
              Chip(
                label: Text(p.name),
                visualDensity: VisualDensity.compact,
                backgroundColor: scheme.secondaryContainer,
              ),
          ],
        ),
        const SizedBox(height: 12),
        for (final g in plan.groups) ...[
          Text(g.group.toUpperCase(),
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(letterSpacing: 1, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final c in g.items)
                Tooltip(
                  message: c.summary,
                  child: Chip(
                    label: Text(c.name),
                    visualDensity: VisualDensity.compact,
                    avatar: c.generated
                        ? null
                        : Icon(Icons.lock_outline,
                            size: 15, color: scheme.onSurfaceVariant),
                    backgroundColor: c.generated
                        ? null
                        : scheme.surfaceVariant,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
        ],
        if (plan.permissions.isNotEmpty) ...[
          const Divider(),
          Text('Device permissions this app will request',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 4),
          for (final perm in plan.permissions)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.shield_outlined),
              title: Text(perm.name),
              subtitle: Text(perm.rationale),
            ),
        ],
        if (plan.gatedNames.isNotEmpty) ...[
          const SizedBox(height: 8),
          Card(
            color: scheme.tertiaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  Icon(Icons.link_off, color: scheme.onTertiaryContainer),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      '${plan.gatedNames.join(', ')} are built into the engine but '
                      'stay off until you connect the required developer accounts '
                      '— nothing is signed, submitted or sent without them.',
                      style: TextStyle(color: scheme.onTertiaryContainer),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
        const SizedBox(height: 12),
        Text(plan.disclosure, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
