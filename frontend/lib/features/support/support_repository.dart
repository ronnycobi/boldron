import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class Ticket {
  final int id;
  final String number;
  final String subject;
  final String status;
  final String category;
  final String priority;
  final int organization;
  final List<TicketMessage> messages;

  const Ticket({
    required this.id,
    required this.number,
    required this.subject,
    required this.status,
    required this.category,
    required this.priority,
    required this.organization,
    this.messages = const [],
  });

  factory Ticket.fromJson(Map<String, dynamic> j) => Ticket(
        id: j['id'] as int,
        number: (j['number'] ?? '') as String,
        subject: (j['subject'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        category: (j['category'] ?? '') as String,
        priority: (j['priority'] ?? '') as String,
        organization: (j['organization'] ?? 0) as int,
        messages: ((j['messages'] as List?) ?? [])
            .map((m) => TicketMessage.fromJson(m as Map<String, dynamic>))
            .toList(),
      );
}

class TicketMessage {
  final int id;
  final String body;
  final String author;
  final bool fromStaff;
  final String createdAt;

  const TicketMessage({
    required this.id,
    required this.body,
    required this.author,
    required this.fromStaff,
    required this.createdAt,
  });

  factory TicketMessage.fromJson(Map<String, dynamic> j) => TicketMessage(
        id: j['id'] as int,
        body: (j['body'] ?? '') as String,
        author: (j['author'] ?? '') as String,
        fromStaff: (j['from_staff'] ?? false) as bool,
        createdAt: (j['created_at'] ?? '') as String,
      );
}

class SupportRepository {
  final ApiClient _api;
  SupportRepository(this._api);

  Future<List<Ticket>> tickets() async {
    final data = await _api.get('support/tickets/');
    return (data as List)
        .map((t) => Ticket.fromJson(t as Map<String, dynamic>))
        .toList();
  }

  Future<Ticket> ticket(int id) async {
    final data = await _api.get('support/tickets/$id/');
    return Ticket.fromJson(data as Map<String, dynamic>);
  }

  Future<Ticket> create({
    required int organization,
    required String subject,
    required String body,
    String category = 'question',
    String priority = 'normal',
  }) async {
    final data = await _api.post('support/tickets/', body: {
      'organization': organization,
      'subject': subject,
      'body': body,
      'category': category,
      'priority': priority,
    });
    return Ticket.fromJson(data as Map<String, dynamic>);
  }

  Future<Ticket> reply(int id, String body) async {
    final data =
        await _api.post('support/tickets/$id/reply/', body: {'body': body});
    return Ticket.fromJson(data as Map<String, dynamic>);
  }
}

final supportRepositoryProvider = Provider<SupportRepository>(
  (ref) => SupportRepository(ref.watch(apiClientProvider)),
);

final ticketsProvider =
    FutureProvider<List<Ticket>>((ref) => ref.watch(supportRepositoryProvider).tickets());

final ticketProvider =
    FutureProvider.family<Ticket, int>((ref, id) => ref.watch(supportRepositoryProvider).ticket(id));
