"""Supervised visual-learning foundations for ARGOS research workflows.

This package is deliberately isolated from the operational webapp.  Importing
``dtwin.learning`` must not load a GPU model or protected labels.
"""

from dtwin.learning.schemas import ProtectedTrainingCase

__all__ = ["ProtectedTrainingCase"]
