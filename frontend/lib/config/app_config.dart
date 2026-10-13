/// Compile-time configuration.
///
/// ALL customer-facing branding comes from here, supplied via `--dart-define`
/// at build time — the same Flutter codebase ships as any brand without code
/// changes (spec §43). Nothing in the app hard-codes a product name. The API
/// base points only at the platform's public API layer; the app never needs to
/// know how that API is implemented (spec §44).
class AppConfig {
  const AppConfig._();

  // --- Branding (from --dart-define, never hard-coded) ---------------------
  static const String appName =
      String.fromEnvironment('APP_NAME', defaultValue: 'Boldron');
  static const String companyName =
      String.fromEnvironment('APP_COMPANY_NAME', defaultValue: '');
  static const String tagline = String.fromEnvironment(
    'APP_TAGLINE',
    defaultValue: 'Build software by describing it.',
  );
  static const String supportEmail =
      String.fromEnvironment('APP_SUPPORT_EMAIL', defaultValue: '');
  static const String supportUrl =
      String.fromEnvironment('APP_SUPPORT_URL', defaultValue: '');
  static const String websiteUrl =
      String.fromEnvironment('APP_WEBSITE_URL', defaultValue: '');

  // --- Backend ------------------------------------------------------------
  /// Platform API base, e.g. https://api.example.com/api/v1
  /// Defaults to a local dev server (Android emulator uses 10.0.2.2).
  /// Must end with a trailing slash (the API client normalizes it either way).
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8020/api/v1/',
  );

  /// Deep-link scheme for push/notification routing (spec §37).
  static const String deepLinkScheme =
      String.fromEnvironment('APP_LINK_SCHEME', defaultValue: 'boldron');
}
