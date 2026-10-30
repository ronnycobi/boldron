import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import 'comments_repository.dart';

/// Project comments (spec §4) on mobile: a team thread with @mentions. Mention a
/// teammate with @handle to notify them — the backend resolves it only to a member
/// of the same org.
class CommentsScreen extends ConsumerStatefulWidget {
  final int projectId;
  const CommentsScreen({super.key, required this.projectId});

  @override
  ConsumerState<CommentsScreen> createState() => _CommentsScreenState();
}

class _CommentsScreenState extends ConsumerState<CommentsScreen> {
  final _body = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _body.dispose();
    super.dispose();
  }

  Future<void> _post() async {
    final body = _body.text.trim();
    if (body.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() => _busy = true);
    try {
      await ref.read(commentsRepositoryProvider).post(widget.projectId, body);
      _body.clear();
      ref.invalidate(commentsProvider(widget.projectId));
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
    final view = ref.watch(commentsProvider(widget.projectId));
    return Scaffold(
      appBar: AppBar(title: const Text('Comments')),
      body: Column(
        children: [
          Expanded(
            child: view.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text(e.toString())),
              data: (v) => RefreshIndicator(
                onRefresh: () async =>
                    ref.refresh(commentsProvider(widget.projectId).future),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (v.comments.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 32),
                        child: Center(child: Text('No comments yet.')),
                      ),
                    for (final c in v.comments) _CommentTile(comment: c),
                    if (v.members.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          const Text('Mention: ',
                              style: TextStyle(fontSize: 12)),
                          for (final m in v.members)
                            ActionChip(
                              label: Text('@${m['handle']}'),
                              visualDensity: VisualDensity.compact,
                              onPressed: () {
                                final t = _body.text;
                                _body.text =
                                    '${t.isEmpty ? '' : '$t '}@${m['handle']} ';
                                _body.selection = TextSelection.collapsed(
                                    offset: _body.text.length);
                              },
                            ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _body,
                      minLines: 1,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        hintText: 'Write a comment… @handle to mention',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _busy ? null : _post,
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CommentTile extends StatelessWidget {
  final Comment comment;
  const _CommentTile({required this.comment});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(comment.author,
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              const Spacer(),
              Text(comment.createdAt.split('T').first,
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
          const SizedBox(height: 2),
          Text(comment.body),
          if (comment.mentions.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Wrap(
                spacing: 4,
                children: [
                  for (final m in comment.mentions)
                    Chip(
                      label: Text('@$m'),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
