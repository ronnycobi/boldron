import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/brand.dart';
import '../../core/api_exception.dart';
import 'releases_repository.dart';

/// Prepare a store listing for one app + provider (spec §16/§17): generate an
/// AI draft from the app's real features, review it, approve, and generate +
/// approve screenshots. Everything is a draft until a human approves; nothing
/// is auto-submitted and live submission stays gated.
class StoreListingScreen extends ConsumerStatefulWidget {
  final int appId;
  final String provider;
  final String providerLabel;
  const StoreListingScreen({
    super.key,
    required this.appId,
    required this.provider,
    required this.providerLabel,
  });

  @override
  ConsumerState<StoreListingScreen> createState() => _StoreListingScreenState();
}

class _StoreListingScreenState extends ConsumerState<StoreListingScreen> {
  bool _busy = false;

  (int, String) get _key => (widget.appId, widget.provider);

  Future<void> _run(Future<void> Function() action, String ok) async {
    setState(() => _busy = true);
    try {
      await action();
      ref.invalidate(storeListingProvider(_key));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(ok)));
      }
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
    final listing = ref.watch(storeListingProvider(_key));
    final repo = ref.read(releasesRepositoryProvider);
    return Scaffold(
      appBar: AppBar(title: Text(widget.providerLabel)),
      body: listing.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e.toString())),
        data: (l) {
          final md = l.metadata;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Listing', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (md == null)
                const Text('No listing yet. Generate a draft from your app.')
              else
                PanelCard(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            if (md.aiGenerated)
                              const Chip(
                                label: Text('AI draft'),
                                visualDensity: VisualDensity.compact,
                              ),
                            const SizedBox(width: 6),
                            Chip(
                              label: Text(md.approved ? 'Approved' : 'Needs review'),
                              visualDensity: VisualDensity.compact,
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (md.appName.isNotEmpty)
                          Text(md.appName,
                              style: Theme.of(context).textTheme.titleMedium),
                        if (md.shortDescription.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(md.shortDescription,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w500)),
                        ],
                        if (md.fullDescription.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text(md.fullDescription),
                        ],
                        if (md.keywords.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text('Keywords: ${md.keywords}',
                              style: Theme.of(context).textTheme.bodySmall),
                        ],
                      ],
                    ),
                ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                children: [
                  FilledButton.tonal(
                    onPressed: _busy
                        ? null
                        : () => _run(
                            () => repo.generateListing(
                                widget.appId, widget.provider),
                            'Draft generated.'),
                    child: Text(md == null ? 'Generate draft' : 'Regenerate'),
                  ),
                  if (md != null && !md.approved)
                    FilledButton(
                      onPressed: _busy
                          ? null
                          : () => _run(
                              () => repo.approveListing(
                                  widget.appId, widget.provider),
                              'Listing approved.'),
                      child: const Text('Approve'),
                    ),
                ],
              ),
              const Divider(height: 36),
              Row(
                children: [
                  Text('Screenshots',
                      style: Theme.of(context).textTheme.titleMedium),
                  const Spacer(),
                  Text('${l.screenshots.length}',
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'Generated from your app’s real screens as layout previews.',
                style: TextStyle(fontSize: 12.5),
              ),
              for (final s in l.screenshots)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                    s.approved ? Icons.check_circle : Icons.image_outlined,
                    color: s.approved ? Colors.green : null,
                  ),
                  title: Text(s.caption.isEmpty ? s.screenName : s.caption),
                ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: [
                  FilledButton.tonal(
                    onPressed: _busy
                        ? null
                        : () => _run(
                            () => repo.generateScreenshots(
                                widget.appId, widget.provider),
                            'Screenshots generated.'),
                    child: Text(
                        l.screenshots.isEmpty ? 'Generate' : 'Regenerate'),
                  ),
                  if (l.screenshots.any((s) => !s.approved))
                    FilledButton(
                      onPressed: _busy
                          ? null
                          : () => _run(
                              () => repo.approveScreenshots(
                                  widget.appId, widget.provider),
                              'Screenshots approved.'),
                      child: const Text('Approve all'),
                    ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}
