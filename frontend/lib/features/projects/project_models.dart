// Typed project models mirroring the ProjectSerializer payload.

class Project {
  final int id;
  final String name;
  final String slug;
  final String description;
  final String status;
  final String mode;
  final int organization;
  final String organizationSlug;

  const Project({
    required this.id,
    required this.name,
    required this.slug,
    required this.description,
    required this.status,
    required this.mode,
    required this.organization,
    required this.organizationSlug,
  });

  factory Project.fromJson(Map<String, dynamic> json) => Project(
        id: json['id'] as int,
        name: (json['name'] ?? '') as String,
        slug: (json['slug'] ?? '') as String,
        description: (json['description'] ?? '') as String,
        status: (json['status'] ?? '') as String,
        mode: (json['mode'] ?? '') as String,
        organization: (json['organization'] ?? 0) as int,
        organizationSlug: (json['organization_slug'] ?? '') as String,
      );
}

/// Live build status for a project (from `projects/<id>/build-status/`).
class BuildStatus {
  final String state;
  final int progress;
  final bool demoMode;
  final List<BuildStep> steps;

  const BuildStatus({
    required this.state,
    required this.progress,
    required this.demoMode,
    required this.steps,
  });

  factory BuildStatus.fromJson(Map<String, dynamic> json) => BuildStatus(
        state: (json['state'] ?? '') as String,
        progress: (json['progress'] ?? 0) as int,
        demoMode: (json['demo_mode'] ?? false) as bool,
        steps: ((json['steps'] as List?) ?? [])
            .map((s) => BuildStep.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}

class BuildStep {
  final String key;
  final String status;
  final String detail;

  const BuildStep({
    required this.key,
    required this.status,
    required this.detail,
  });

  factory BuildStep.fromJson(Map<String, dynamic> json) => BuildStep(
        key: (json['key'] ?? '') as String,
        status: (json['status'] ?? '') as String,
        detail: (json['detail'] ?? '') as String,
      );
}
