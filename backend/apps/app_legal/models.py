"""Generated legal documents for a customer's app (spec §63-64).

These are DRAFTS composed from the project's actual configuration. They are never
presented as legal advice or guaranteed compliance — every generated document
carries a prominent disclaimer to have it reviewed by qualified counsel.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class GeneratedLegalDoc(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE,
        related_name="generated_legal_docs")
    doc_type = models.CharField(max_length=60)        # privacy_policy, terms_of_service, …
    content = models.TextField()
    disclaimer = models.TextField(blank=True)
    reviewed = models.BooleanField(default=False)     # a person confirmed counsel review
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="generated_legal_docs")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["doc_type", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "doc_type"],
                                    name="unique_generated_doc_per_project")
        ]

    def __str__(self):
        return f"{self.doc_type} for project {self.project_id}"
