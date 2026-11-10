"""
Backward-compatibility model for research tasks.

Some integration and performance tests still import `ResearchTask` from this
module. The project already defines the task schema in
`apps/api/src/models/task.py`, so we simply re-export the existing models
instead of duplicating schema definitions.
"""

from .task import DeepResearchTask, TaskStatus

# Alias the concrete Beanie model so older imports keep working.
ResearchTask = DeepResearchTask

__all__ = ["ResearchTask", "TaskStatus"]
