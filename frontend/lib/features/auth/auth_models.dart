// Typed models for the authenticated user and the orgs they belong to.
// These mirror the `user` payload the API returns from auth endpoints and
// `me/` — parsing lives here, never in widgets (spec §33).
import 'package:flutter/material.dart' show ThemeMode;

class OrgSummary {
  final int id;
  final String name;
  final String slug;
  final String role;

  const OrgSummary({
    required this.id,
    required this.name,
    required this.slug,
    required this.role,
  });

  bool get canManage => role == 'owner' || role == 'admin';

  factory OrgSummary.fromJson(Map<String, dynamic> json) => OrgSummary(
        id: json['id'] as int,
        name: (json['name'] ?? '') as String,
        slug: (json['slug'] ?? '') as String,
        role: (json['role'] ?? 'member') as String,
      );
}

class AuthUser {
  final int id;
  final String email;
  final String fullName;
  final String displayName;
  final String initials;
  final String avatarUrl;
  final bool emailVerified;
  final List<OrgSummary> organizations;
  // Profile details + accessibility preferences (spec §4/§11).
  final String jobTitle;
  final String pronouns;
  final String bio;
  final String fontScale; // sm | md | lg | xl
  final bool reduceMotion;
  final String theme; // dark | light | system

  const AuthUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.displayName,
    required this.initials,
    required this.avatarUrl,
    required this.emailVerified,
    required this.organizations,
    this.jobTitle = '',
    this.pronouns = '',
    this.bio = '',
    this.fontScale = 'md',
    this.reduceMotion = false,
    this.theme = 'dark',
  });

  ThemeMode get themeMode => theme == 'light'
      ? ThemeMode.light
      : theme == 'system'
          ? ThemeMode.system
          : ThemeMode.dark;

  /// Text-scale multiplier for the chosen size (mirrors the backend factors).
  double get fontScaleFactor => const {
        'sm': 0.9,
        'md': 1.0,
        'lg': 1.15,
        'xl': 1.3,
      }[fontScale] ??
      1.0;

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: json['id'] as int,
        email: (json['email'] ?? '') as String,
        fullName: (json['full_name'] ?? '') as String,
        displayName: (json['display_name'] ?? json['email'] ?? '') as String,
        initials: (json['initials'] ?? '') as String,
        avatarUrl: (json['avatar_url'] ?? '') as String,
        emailVerified: (json['email_verified'] ?? false) as bool,
        organizations: ((json['organizations'] as List?) ?? [])
            .map((o) => OrgSummary.fromJson(o as Map<String, dynamic>))
            .toList(),
        jobTitle: (json['job_title'] ?? '') as String,
        pronouns: (json['pronouns'] ?? '') as String,
        bio: (json['bio'] ?? '') as String,
        fontScale: (json['font_scale'] ?? 'md') as String,
        reduceMotion: (json['reduce_motion'] ?? false) as bool,
        theme: (json['theme'] ?? 'dark') as String,
      );
}
