IDLE_RESET_THRESHOLD = 300
ACTIVE_TRIGGER_THRESHOLD = 3600


def update_usage_seconds(accumulated, idle_seconds, elapsed_since_last_poll, idle_threshold=IDLE_RESET_THRESHOLD):
    """유휴 시간이 임계값 이상이면 누적 사용 시간을 0으로 리셋하고,
    아니면 이번 폴링 간격만큼 누적 사용 시간에 더한다."""
    if idle_seconds >= idle_threshold:
        return 0
    return accumulated + elapsed_since_last_poll


def should_trigger_reminder(accumulated, active_threshold=ACTIVE_TRIGGER_THRESHOLD):
    return accumulated >= active_threshold
