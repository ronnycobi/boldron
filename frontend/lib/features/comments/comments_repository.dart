import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

/// A project comment with its resolved @mentions.
class Comment {
  final int id;
  final String author;
  final String body;
  final String createdAt;
  final List<String> mentions;

  const Comment({
    required this.id,
    required this.author,
    required this.body,
    required this.createdAt,
    this.mentions = const [],
  });

  factory Comment.fromJson(Map<String, dynamic> j) => Comment(
        id: j['id'] as int,
        author: (j['author'] ?? 'Unknown') as String,
        body: (j['body'] ?? '') as String,
        createdAt: (j['created_at'] ?? '') as String,
        mentions:
            ((j['mentions'] as List?) ?? []).map((e) => e.toString()).toList(),
      );
}

class CommentsView {
  final List<Comment> comments;
  final List<Map<String, dynamic>> members; // {name, handle}
  const CommentsView({required this.comments, required this.members});

  factory CommentsView.fromJson(Map<String, dynamic> j) => CommentsView(
        comments: ((j['comments'] as List?) ?? [])
            .map((c) => Comment.fromJson(c as Map<String, dynamic>))
            .toList(),
        members: ((j['members'] as List?) ?? [])
            .map((m) => (m as Map).cast<String, dynamic>())
            .toList(),
      );
}

class CommentsRepository {
  final ApiClient _api;
  CommentsRepository(this._api);

  Future<CommentsView> comments(int projectId) async {
    final data = await _api.get('projects/$projectId/comments/');
    return CommentsView.fromJson((data as Map).cast<String, dynamic>());
  }

  Future<void> post(int projectId, String body) =>
      _api.post('projects/$projectId/comments/', body: {'body': body});
}

final commentsRepositoryProvider = Provider<CommentsRepository>(
  (ref) => CommentsRepository(ref.watch(apiClientProvider)),
);

final commentsProvider =
    FutureProvider.family<CommentsView, int>((ref, projectId) {
  return ref.watch(commentsRepositoryProvider).comments(projectId);
});
