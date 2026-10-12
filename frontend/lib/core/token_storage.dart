import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The JWT pair store. An interface so the networking layer can be unit-tested
/// with an in-memory fake, while the app uses the platform-secure backend.
abstract class TokenStorage {
  Future<void> save({required String access, required String refresh});
  Future<void> saveAccess(String access);
  Future<String?> readAccess();
  Future<String?> readRefresh();
  Future<bool> hasTokens();
  Future<void> clear();
}

/// Secure, platform-backed storage (Keychain on iOS, Keystore on Android).
/// Tokens are never written to plain preferences or logs (spec §34).
class SecureTokenStorage implements TokenStorage {
  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';

  final FlutterSecureStorage _storage;

  SecureTokenStorage([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  @override
  Future<void> save({required String access, required String refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  @override
  Future<void> saveAccess(String access) =>
      _storage.write(key: _accessKey, value: access);

  @override
  Future<String?> readAccess() => _storage.read(key: _accessKey);

  @override
  Future<String?> readRefresh() => _storage.read(key: _refreshKey);

  @override
  Future<bool> hasTokens() async => (await readRefresh()) != null;

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
