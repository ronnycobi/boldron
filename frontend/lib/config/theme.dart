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

  // --- Light theme (mirrors the web dashboard's light palette) -------------
  static const lBg = Color(0xFFF7F9FD);
  static const lPanel = Color(0xFFFFFFFF);
  static const lPanel2 = Color(0xFFF3F6FD);
  static const lLine = Color(0xFFE6EBF5);
  static const lLine2 = Color(0xFFD6DEED);
  static const lInk = Color(0xFF151D2F);
  static const lInk2 = Color(0xFF3C4761);
  static const lMuted = Color(0xFF697590);
  static const lBrand = Color(0xFF4A69E0);
  static const lBrand2 = Color(0xFF8A5CF0);

  static ThemeData light() {
    final scheme = ColorScheme.fromSeed(
      seedColor: lBrand,
      brightness: Brightness.light,
    ).copyWith(
      primary: lBrand,
      onPrimary: Colors.white,
      secondary: lBrand2,
      surface: lPanel,
      onSurface: lInk,
      onSurfaceVariant: lMuted,
      outline: lLine2,
      outlineVariant: lLine,
      error: const Color(0xFFD83A3A),
      primaryContainer: const Color(0xFFE5ECFF),
      onPrimaryContainer: const Color(0xFF1B2A5E),
      tertiaryContainer: const Color(0xFFF1EAFF),
      onTertiaryContainer: const Color(0xFF3A2A6B),
    );
    final text = Typography.blackMountainView.apply(
      bodyColor: lInk,
      displayColor: lInk,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: scheme,
      scaffoldBackgroundColor: lBg,
      canvasColor: lBg,
      textTheme: text,
      dividerColor: lLine,
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        foregroundColor: lInk,
        elevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardTheme(
        color: lPanel,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: lLine),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: lBrand,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(50),
          textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: lInk,
          minimumSize: const Size.fromHeight(48),
          side: const BorderSide(color: lLine2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: lBrand),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: lPanel2,
        hintStyle: const TextStyle(color: lMuted),
        labelStyle: const TextStyle(color: lMuted),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: lLine2),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: lLine2),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: lBrand, width: 1.5),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: lPanel2,
        side: const BorderSide(color: lLine2),
        labelStyle: const TextStyle(color: lInk2, fontSize: 12.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(99)),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: lPanel,
        surfaceTintColor: Colors.transparent,
        indicatorColor: lBrand.withOpacity(0.14),
        labelTextStyle: MaterialStateProperty.all(
          const TextStyle(fontSize: 11.5, color: lInk2),
        ),
        iconTheme: MaterialStateProperty.resolveWith(
          (states) => IconThemeData(
            color: states.contains(MaterialState.selected) ? lBrand : lMuted,
          ),
        ),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: lPanel,
        selectedIconTheme: IconThemeData(color: lBrand),
        unselectedIconTheme: IconThemeData(color: lMuted),
        selectedLabelTextStyle: TextStyle(color: lInk),
        unselectedLabelTextStyle: TextStyle(color: lMuted),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: lBrand,
        linearTrackColor: lPanel2,
      ),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: Color(0xFF1C2333),
        contentTextStyle: TextStyle(color: Colors.white),
      ),
      dialogTheme: DialogTheme(
        backgroundColor: lPanel,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      listTileTheme: const ListTileThemeData(iconColor: lInk2),
    );
  }
}
