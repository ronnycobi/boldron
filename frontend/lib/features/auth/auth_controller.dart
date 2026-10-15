import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/token_storage.dart';
import 'auth_models.dart';
import 'auth_repository.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

/// Immutable auth state the whole app routes on.
class AuthState {
  final AuthStatus status;
  final AuthUser? user;
  final bool busy;
  final String? error;
  // Non-null between the password step and the MFA code step.
  final String? mfaToken;

  const AuthState({
    this.status = AuthStatus.unknown,
    this.user,
    this.busy = false,
    this.error,
    this.mfaToken,
  });

  bool get mfaRequired => mfaToken != null;

  AuthState copyWith({
    AuthStatus? status,
    AuthUser? user,
    bool? busy,
    String? error,
    bool clearError = false,
    String? mfaToken,
    bool clearMfa = false,
  }) =>
      AuthState(
        status: status ?? this.status,
        user: user ?? this.user,
        busy: busy ?? this.busy,
        error: clearError ? null : (error ?? this.error),
        mfaToken: clearMfa ? null : (mfaToken ?? this.mfaToken),
      );
}

/// Owns the sign-in lifecycle: restore a session on launch, log in / register,
/// and log out. Presentation reads this; it never calls the repository itself.
class AuthController extends StateNotifier<AuthState> {
  final AuthRepository _repo;
  final TokenStorage _tokens;

  AuthController(this._repo, this._tokens) : super(const AuthState()) {
    bootstrap();
  }

  /// On launch: if we have a refresh token, try to load the user; the API
  /// client refreshes the access token transparently if it has expired.
  Future<void> bootstrap() async {
    if (!await _tokens.hasTokens()) {
      state = state.copyWith(status: AuthStatus.unauthenticated);
      return;
    }
    try {
      final user = await _repo.me();
      state = state.copyWith(status: AuthStatus.authenticated, user: user);
    } on ApiException {
      await _tokens.clear();
      state = state.copyWith(status: AuthStatus.unauthenticated);
    }
  }

  /// Password step. Returns true when the user is fully signed in; returns false
  /// when MFA is required (then [AuthState.mfaRequired] is set and the UI should
  /// navigate to the code challenge) or on error (then [AuthState.error] is set).
  Future<bool> login(String email, String password) async {
    state = state.copyWith(busy: true, clearError: true, clearMfa: true);
    try {
      final outcome = await _repo.login(email, password);
      if (outcome.mfaRequired) {
        state = state.copyWith(busy: false, mfaToken: outcome.mfaToken);
        return false;
      }
      state = state.copyWith(
        status: AuthStatus.authenticated, user: outcome.user, busy: false);
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(busy: false, error: e.firstFieldError ?? e.message);
      return false;
    }
  }

  /// Second step of MFA login: verify a TOTP or recovery code.
  Future<bool> verifyMfa(String code) async {
    final token = state.mfaToken;
    if (token == null) return false;
    state = state.copyWith(busy: true, clearError: true);
    try {
      final user = await _repo.verifyMfa(token, code);
      state = state.copyWith(
        status: AuthStatus.authenticated, user: user, busy: false, clearMfa: true);
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(busy: false, error: e.firstFieldError ?? e.message);
      return false;
    }
  }

  /// Abandon a pending MFA challenge (user backed out to the sign-in screen).
  void cancelMfa() => state = state.copyWith(clearMfa: true, clearError: true);

  Future<bool> register({
    required String email,
    required String password,
    String fullName = '',
    String orgName = '',
  }) =>
      _run(() => _repo.register(
            email: email,
            password: password,
            fullName: fullName,
            orgName: orgName,
          ));

  Future<void> logout() async {
    await _repo.logout();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  /// Called by the API client when a refresh fails mid-session.
  void onSessionExpired() {
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  Future<void> refreshUser() async {
    try {
      state = state.copyWith(user: await _repo.me());
    } on ApiException {
      // keep the current user on a transient failure
    }
  }

  /// Update the cached user after an account operation returned a fresh copy.
  void setUser(AuthUser user) {
    state = state.copyWith(user: user);
  }

  Future<bool> _run(Future<AuthUser> Function() action) async {
    state = state.copyWith(busy: true, clearError: true);
    try {
      final user = await action();
      state = state.copyWith(
        status: AuthStatus.authenticated,
        user: user,
        busy: false,
      );
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(
        busy: false,
        error: e.firstFieldError ?? e.message,
      );
      return false;
    }
  }
}
