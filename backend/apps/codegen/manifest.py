"""The run manifest filename for generated projects.

Scaffolds write this file into every generated project; the preview runner and
codegen read it to learn how to run and test the project. The name is brand-
neutral on purpose — it ships inside the customer's own repository/export, so it
must not carry the platform's brand. Single source of truth for all writers and
readers.
"""

MANIFEST_FILENAME = "app.manifest.json"
