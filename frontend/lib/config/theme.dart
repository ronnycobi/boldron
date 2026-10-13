import 'package:flutter/material.dart';

/// App theme matched to the web dashboard's design language: a dark navy ground,
/// a blue→purple brand gradient, bordered panels, and the same status colors.
/// The app is dark-first (like the website) regardless of the system setting.
class AppTheme {
  const AppTheme._();

  // Web tokens (backend base_dash.html).
  static const bg = Color(0xFF080C18);
  static const bg2 = Color(0xFF0B1124);
  static const panel = Color(0xFF111A30);
  static const panel2 = Color(0xFF0E1526);
  static const line = Color(0xFF1D2743);
  static const line2 = Color(0xFF26324F);
  static const ink = Color(0xFFE8EDFB);
  static const ink2 = Color(0xFFC3CBE0);
  static const muted = Color(0xFF7F8AA8);
  static const brand = Color(0xFF4F7CFF);
  static const brand2 = Color(0xFF9B6BFF);

  static const ok = Color(0xFF34D399);
  static const fail = Color(0xFFF87171);
  static const run = Color(0xFF60A5FA);
  static const wait = Color(0xFFFBBF24);

  /// The signature brand gradient (135°, blue → purple).
  static const brandGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [brand, brand2],
  );

  static ThemeData dark() {
    final scheme = ColorScheme.fromSeed(
      seedColor: brand,
      brightness: Brightness.dark,
    ).copyWith(
      primary: brand,
      onPrimary: Colors.white,
      secondary: brand2,
      surface: panel,
      onSurface: ink,
      onSurfaceVariant: muted,
      outline: line2,
      outlineVariant: line,
      error: fail,
      primaryContainer: const Color(0xFF1B2748),
      onPrimaryContainer: const Color(0xFFCADAFF),
      tertiaryContainer: const Color(0xFF2A2340),
      onTertiaryContainer: const Color(0xFFE6DBFF),
    );

    // The web stack is system-first (-apple-system / Roboto / Inter), so the
    // platform default font is the right match — nothing to bundle.
    final text = Typography.whiteMountainView.apply(
      bodyColor: ink,
      displayColor: ink,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: bg,
      canvasColor: bg,
      textTheme: text,
      dividerColor: line,
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        foregroundColor: ink,
        elevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardTheme(
        color: panel,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: line),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: brand,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(50),
          textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: ink,
          minimumSize: const Size.fromHeight(48),
          side: const BorderSide(color: line2),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: brand),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: panel2,
        hintStyle: const TextStyle(color: muted),
        labelStyle: const TextStyle(color: muted),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: line2),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: line2),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: brand, width: 1.5),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: panel2,
        side: const BorderSide(color: line2),
        labelStyle: const TextStyle(color: ink2, fontSize: 12.5),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(99)),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: panel2,
        surfaceTintColor: Colors.transparent,
        indicatorColor: brand.withOpacity(0.18),
        labelTextStyle: MaterialStateProperty.all(
          const TextStyle(fontSize: 11.5, color: ink2),
        ),
        iconTheme: MaterialStateProperty.resolveWith(
          (states) => IconThemeData(
            color: states.contains(MaterialState.selected) ? brand : muted,
          ),
        ),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: panel2,
        selectedIconTheme: IconThemeData(color: brand),
        unselectedIconTheme: IconThemeData(color: muted),
        selectedLabelTextStyle: TextStyle(color: ink),
        unselectedLabelTextStyle: TextStyle(color: muted),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: brand,
        linearTrackColor: panel2,
      ),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: panel,
        contentTextStyle: TextStyle(color: ink),
      ),
      dialogTheme: DialogTheme(
        backgroundColor: panel,
        surfaceTintColor: Colors.transparent,
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      listTileTheme: const ListTileThemeData(iconColor: ink2),
    );
  }
}
