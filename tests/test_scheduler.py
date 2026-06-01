from unittest.mock import MagicMock, patch
from keydaemon.scheduler import run_scheduled
from keydaemon._types import LOOP_FOREVER
from keydaemon.actions import _SelfStop


def _ctrl():
    return MagicMock()


def test_runs_actions_once():
    action = MagicMock()
    run_scheduled([action], interval=None, repeat_times=1, jitter=0.0,
                  controller=_ctrl(), stop_requested=lambda: False)
    action.execute.assert_called_once()


def test_repeats_n_times():
    action = MagicMock()
    run_scheduled([action], interval=None, repeat_times=3, jitter=0.0,
                  controller=_ctrl(), stop_requested=lambda: False)
    assert action.execute.call_count == 3


def test_stop_requested_halts():
    from itertools import count
    c = count()
    def stop_after_two():
        return next(c) >= 2

    action = MagicMock()
    run_scheduled([action], interval=None, repeat_times=LOOP_FOREVER, jitter=0.0,
                  controller=_ctrl(), stop_requested=stop_after_two)
    assert action.execute.call_count <= 3


def test_interval_sleeps_between_iterations():
    action = MagicMock()
    with patch("keydaemon.scheduler._interruptible_sleep") as mock_sleep:
        run_scheduled([action], interval=5.0, repeat_times=2, jitter=0.0,
                      controller=_ctrl(), stop_requested=lambda: False)
    assert mock_sleep.called
    # called once between iteration 1 and 2 (not after the final iteration)
    assert mock_sleep.call_count == 1


def test_self_stop_exits_cleanly():
    action = MagicMock()
    action.execute.side_effect = _SelfStop("test-token")
    # Should not raise — _SelfStop is caught and causes clean return
    run_scheduled([action], interval=None, repeat_times=LOOP_FOREVER, jitter=0.0,
                  controller=_ctrl(), stop_requested=lambda: False)
    action.execute.assert_called_once()


def test_jitter_does_not_go_negative():
    action = MagicMock()
    with patch("keydaemon.scheduler._interruptible_sleep") as mock_sleep:
        run_scheduled([action], interval=1.0, repeat_times=2, jitter=100.0,
                      controller=_ctrl(), stop_requested=lambda: False)
    # sleep delay must be >= 0
    for call in mock_sleep.call_args_list:
        assert call.args[0] >= 0
