import re
from typing import Optional

# Valid PostgreSQL timezone offsets (integer representation)
# e.g., -500 represents -05:00, +330 represents +03:30
# Reference: https://docs.oracle.com/cd/E19563-01/819-4437/anovd/index.html
POSTGRES_VALID_TIMEZONES = {
    -1200, -1100, -1000, -930, -900, -800, -700,
    -600, -500, -400, -300, -230, -200, -100, 000,
    100, 200, 300, 330, 400, 430, 500, 530, 545, 600,
    630, 700, 800, 845, 900, 930, 1000, 1030, 1100, 1200,
    1245, 1300, 1400
}


def fix_invalid_timezone(timestamp_str: str, valid_timezones: set = None) -> Optional[str]:
    """
    Check if a timestamp has an invalid PostgreSQL timezone and return the corrected version.

    Args:
        timestamp_str: Timestamp in format "YYYY-MM-DD HH:MM:SS ±HHMM"
        valid_timezones: Set of valid timezone offsets as integers.
            Defaults to POSTGRES_VALID_TIMEZONES.

    Returns:
        Corrected timestamp with +0000 timezone if original was invalid,
        None if the original timezone was valid.
    """
    if valid_timezones is None:
        valid_timezones = POSTGRES_VALID_TIMEZONES

    segments = re.split(" ", timestamp_str)
    tzdata = segments.pop()

    if ":" in tzdata:
        tzdata = tzdata.replace(":", "")

    try:
        tz_int = int(tzdata)
    except ValueError:
        # Can't parse timezone as int (e.g., "UTC", "EST"), treat as invalid
        segments.append("+0000")
        return " ".join(segments)

    if tz_int not in valid_timezones:
        segments.append("+0000")
        return " ".join(segments)

    return None
