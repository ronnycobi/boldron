import 'package:boldron_app/core/token_storage.dart';

/// In-memory token store for tests (no platform channels).
class FakeTokenStorage implements TokenStorage {
  String? access;
  String? refresh;

  FakeTokenStorage({this.access, this.refresh});

  @override
  Future<void> save({required String access, required String refresh}) async {
    this.access = access;
    this.refresh = refresh;
  }

  @override
  Future<void> saveAccess(String access) async => this.access = access;

  @override
  Future<String?> readAccess() async => access;

  @override
  Future<String?> readRefresh() async => refresh;

  @override
  Future<bool> hasTokens() async => refresh != null;

  @override
  Future<void> clear() async {
    access = null;
    refresh = null;
  }
}
