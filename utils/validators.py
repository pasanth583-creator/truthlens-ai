from typing import Tuple, Optional

def validate_input_text(
    raw_text: any,
    min_length: int = 5,
    max_length: int = 10000
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate claim or article text input.

    Returns:
        tuple: (is_valid: bool, cleaned_text: Optional[str], error_message: Optional[str])
    """
    if raw_text is None:
        return False, None, "Input text is required."

    if not isinstance(raw_text, str):
        return False, None, "Input must be a valid text string."

    cleaned = raw_text.strip()

    if not cleaned:
        return False, None, "Input text cannot be empty or whitespace only."

    if len(cleaned) < min_length:
        return (
            False,
            None,
            f"Input text is too short. Please provide at least {min_length} characters (found {len(cleaned)})."
        )

    if len(cleaned) > max_length:
        return (
            False,
            None,
            f"Input text exceeds the maximum allowed length of {max_length} characters (found {len(cleaned)})."
        )

    # Check minimum word count (at least 2 words)
    words = cleaned.split()
    if len(words) < 2:
        return False, None, "Please provide a complete statement or claim (at least two words)."

    return True, cleaned, None
