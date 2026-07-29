"""Developer metrics: task phases, cross-file coordination."""

import re
from collections import Counter
from typing import Dict, List


def classify_task_phase(text: str) -> Dict[str, int]:
    """
    Heuristic classification of development task phases.

    Args:
        text: Developer message text

    Returns:
        dict: {phase: count}
    """
    text_lower = text.lower()

    phases = {
        "planning": 0,
        "implementation": 0,
        "debugging": 0,
        "review": 0,
        "testing": 0,
        "refactoring": 0,
    }

    # Planning patterns
    if re.search(r'design|architecture|plan|approach|strategy|component|structure', text_lower):
        phases["planning"] += 1

    # Implementation patterns
    if re.search(r'implement|code|write|add|create|function|method|class', text_lower):
        phases["implementation"] += 1

    # Debugging patterns
    if re.search(r'bug|error|fix|issue|stack trace|failing|broken|debug', text_lower):
        phases["debugging"] += 1

    # Review patterns
    if re.search(r'review|feedback|concern|comment|nit|looks good|suggest|approve', text_lower):
        phases["review"] += 1

    # Testing patterns
    if re.search(r'test|unit test|integration|assertion|coverage|verify|validate', text_lower):
        phases["testing"] += 1

    # Refactoring patterns
    if re.search(r'refactor|rename|clean|simplify|extract|modularize|consolidate', text_lower):
        phases["refactoring"] += 1

    return phases


def compute_cross_file_coordination(
    detected_files: List[Dict]
) -> int:
    """
    Count of distinct files mentioned and coordination factor.

    Args:
        detected_files: List of detected file objects

    Returns:
        int: Coordination score
    """
    if not detected_files:
        return 0

    if isinstance(detected_files[0], str):
        unique_files = set(detected_files)
    else:
        unique_files = set(f.get("path", f.get("name", "")) for f in detected_files)

    return len(unique_files)


def compute_architectural_scope(
    detected_files: List[Dict],
    detected_lines: int
) -> str:
    """
    Classify whether changes are local or system-wide.

    Args:
        detected_files: Files mentioned
        detected_lines: Approximate lines of code

    Returns:
        str: "local", "subsystem", or "system"
    """
    file_count = len(set(f.get("path", "") for f in detected_files))

    if file_count == 0:
        return "unknown"
    elif file_count == 1 and detected_lines < 100:
        return "local"
    elif file_count <= 3 and detected_lines < 500:
        return "subsystem"
    else:
        return "system"


def compute_review_density(
    message_history: List[str]
) -> float:
    """
    Fraction of messages containing review comments.

    Args:
        message_history: List of agent messages

    Returns:
        float: 0-1 review density
    """
    if not message_history:
        return 0.0

    review_messages = sum(
        1 for msg in message_history
        if re.search(r'review|feedback|comment|suggest|looks good|approve', msg.lower())
    )

    return min(1.0, review_messages / len(message_history))


def compute_implementation_momentum(
    message_history: List[str]
) -> float:
    """
    Ratio of implementation to other task phases.

    Args:
        message_history: List of agent messages

    Returns:
        float: 0-1 momentum (higher = more implementation focus)
    """
    if not message_history:
        return 0.0

    impl_count = sum(
        1 for msg in message_history
        if re.search(r'implement|code|write|add|function', msg.lower())
    )

    total_dev = sum(
        1 for msg in message_history
        if re.search(r'design|plan|implement|debug|review|test|refactor', msg.lower())
    )

    if total_dev == 0:
        return 0.0

    return min(1.0, impl_count / total_dev)


def extract_file_list(message: str) -> List[str]:
    """
    Extract file paths from a message.

    Args:
        message: Text containing file references

    Returns:
        list: File paths found
    """
    # Match common file extensions
    pattern = r'\b[\w.-]+\.(py|js|ts|java|cpp|c|go|rb|php|sql|html|css|json|yaml|yml|md)\b'

    files = re.findall(pattern, message, re.IGNORECASE)

    return list(set(files))


def compute_file_concentration(detected_files: List[Dict]) -> float:
    """
    How concentrated are changes in few files vs. spread out.

    Args:
        detected_files: List of file objects

    Returns:
        float: 0 (spread) to 1 (concentrated)
    """
    if not detected_files:
        return 0.0

    # Count mentions per file
    file_mentions = Counter(f.get("path", f.get("name", "")) for f in detected_files)

    if len(file_mentions) == 0:
        return 0.0

    # Compute concentration
    total_mentions = sum(file_mentions.values())
    max_mentions = max(file_mentions.values())

    concentration = max_mentions / total_mentions if total_mentions > 0 else 0

    return min(1.0, concentration)
