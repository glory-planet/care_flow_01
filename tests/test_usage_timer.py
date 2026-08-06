from usage_timer import should_trigger_reminder, update_usage_seconds


def test_update_usage_seconds_accumulates_when_active():
    result = update_usage_seconds(accumulated=100, idle_seconds=2, elapsed_since_last_poll=10)
    assert result == 110


def test_update_usage_seconds_resets_when_idle_past_threshold():
    result = update_usage_seconds(accumulated=1000, idle_seconds=301, elapsed_since_last_poll=10, idle_threshold=300)
    assert result == 0


def test_update_usage_seconds_does_not_reset_when_idle_under_threshold():
    result = update_usage_seconds(accumulated=1000, idle_seconds=299, elapsed_since_last_poll=10, idle_threshold=300)
    assert result == 1010


def test_should_trigger_reminder_true_at_threshold():
    assert should_trigger_reminder(3600, active_threshold=3600) is True


def test_should_trigger_reminder_false_under_threshold():
    assert should_trigger_reminder(3599, active_threshold=3600) is False
