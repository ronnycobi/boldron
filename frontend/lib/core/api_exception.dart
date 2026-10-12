/// A single, typed error type the whole app understands.
///
/// The API client converts every transport/HTTP failure into one of these, so
/// UI and controllers never deal with Dio or raw status codes. Field-level
/// validation errors (the backend returns `{field: [messages]}`) are surfaced
/// in [fieldErrors] so forms can show them inline.
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final Map<String, List<String>> fieldErrors;

  /// True for 401 — the caller should refresh or sign in again.
  final bool isUnauthorized;

  /// True when the request never reached the server (offline/timeout).
  final bool isNetwork;

  ApiException(
    this.message, {
    this.statusCode,
    this.fieldErrors = const {},
    this.isUnauthorized = false,
    this.isNetwork = false,
  });

  /// The first field error, if any — handy for a single-line form message.
  String? get firstFieldError {
    for (final messages in fieldErrors.values) {
      if (messages.isNotEmpty) return messages.first;
    }
    return null;
  }

  @override
  String toString() => message;
}
