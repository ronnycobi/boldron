import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/providers.dart';

class Member {
  final int userId;
  final String email;
  final String displayName;
  final String role;

  const Member({
    required this.userId,
    required this.email,
    required this.displayName,
    required this.role,
  });

  factory Member.fromJson(Map<String, dynamic> j) {
    final user = (j['user'] as Map).cast<String, dynamic>();
    return Member(
      userId: user['id'] as int,
      email: (user['email'] ?? '') as String,
      displayName: (user['display_name'] ?? user['email'] ?? '') as String,
      role: (j['role'] ?? 'member') as String,
    );
  }
}

class Invitation {
  final int id;
  final String email;
  final String role;
  final String status;
  final bool isPending;

  const Invitation({
    required this.id,
    required this.email,
    required this.role,
    required this.status,
    required this.isPending,
  });

  factory Invitation.fromJson(Map<String, dynamic> j) => Invitation(
        id: j['id'] as int,
        email: (j['email'] ?? '') as String,
        role: (j['role'] ?? '') as String,
        status: (j['status'] ?? '') as String,
        isPending: (j['is_pending'] ?? false) as bool,
      );
}

class TeamRepository {
  final ApiClient _api;
  TeamRepository(this._api);

  Future<List<Member>> members(int orgId) async {
    final data = await _api.get('organizations/$orgId/members/');
    return (data as List)
        .map((m) => Member.fromJson(m as Map<String, dynamic>))
        .toList();
  }

  Future<List<Invitation>> invitations(int orgId) async {
    final data = await _api.get('organizations/$orgId/invitations/');
    return (data as List)
        .map((i) => Invitation.fromJson(i as Map<String, dynamic>))
        .toList();
  }

  Future<void> invite(int orgId, String email, {String role = 'member'}) =>
      _api.post('organizations/$orgId/invitations/',
          body: {'email': email, 'role': role});

  Future<void> removeMember(int orgId, int userId) =>
      _api.delete('organizations/$orgId/members/$userId/');

  Future<void> changeRole(int orgId, int userId, String role) =>
      _api.patch('organizations/$orgId/members/$userId/', body: {'role': role});

  /// Organization general details (incl. description + the caller's permissions).
  Future<Map<String, dynamic>> organization(int orgId) async {
    final data = await _api.get('organizations/$orgId/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<Map<String, dynamic>> updateOrganization(
      int orgId, Map<String, dynamic> fields) async {
    final data = await _api.patch('organizations/$orgId/', body: fields);
    return (data as Map).cast<String, dynamic>();
  }

  /// The role → permission matrix (reference) plus the caller's permissions.
  Future<Map<String, dynamic>> roles(int orgId) async {
    final data = await _api.get('organizations/$orgId/roles/');
    return (data as Map).cast<String, dynamic>();
  }

  /// AI preferences + the connected providers/models + generation status.
  Future<Map<String, dynamic>> aiSettings(int orgId) async {
    final data = await _api.get('organizations/$orgId/ai/');
    return (data as Map).cast<String, dynamic>();
  }

  Future<void> updateAiSettings(int orgId,
          {String provider = '', String model = ''}) =>
      _api.patch('organizations/$orgId/ai/',
          body: {'preferred_provider': provider, 'preferred_model': model});

  /// Read-only audit log for the organization (manager-gated server-side).
  Future<List<Map<String, dynamic>>> audit(int orgId) async {
    final data = await _api.get('organizations/$orgId/audit/');
    return ((data as Map)['events'] as List)
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
  }
}

final teamRepositoryProvider = Provider<TeamRepository>(
  (ref) => TeamRepository(ref.watch(apiClientProvider)),
);

final membersProvider =
    FutureProvider.family<List<Member>, int>((ref, orgId) {
  return ref.watch(teamRepositoryProvider).members(orgId);
});

final invitationsProvider =
    FutureProvider.family<List<Invitation>, int>((ref, orgId) {
  return ref.watch(teamRepositoryProvider).invitations(orgId);
});

final organizationProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, orgId) {
  return ref.watch(teamRepositoryProvider).organization(orgId);
});

final orgRolesProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, orgId) {
  return ref.watch(teamRepositoryProvider).roles(orgId);
});

final orgAiProvider =
    FutureProvider.family<Map<String, dynamic>, int>((ref, orgId) {
  return ref.watch(teamRepositoryProvider).aiSettings(orgId);
});

final orgAuditProvider =
    FutureProvider.family<List<Map<String, dynamic>>, int>((ref, orgId) {
  return ref.watch(teamRepositoryProvider).audit(orgId);
});
