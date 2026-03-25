"""Unit tests for terminal session management.

Tests cover:
- TerminalSession: Lifecycle, port management, state tracking
- TerminalSessionManager: Multi-session management, cleanup
"""

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from demorec.modes.terminal import TerminalSession, TerminalSessionManager


class TestTerminalSession:
    """Test TerminalSession class."""

    def test_init_assigns_unique_port(self):
        """Should assign a free port on creation."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession("test")
            assert session.port == 8080
            assert session.name == "test"

    def test_init_process_is_none(self):
        """Should initialize with no process."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            assert session._process is None

    def test_is_running_false_when_no_process(self):
        """Should return False when no process exists."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            assert session.is_running() is False

    def test_is_running_true_when_process_alive(self):
        """Should return True when process is running."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            mock_process = MagicMock()
            mock_process.poll.return_value = None  # None means still running
            session._process = mock_process
            assert session.is_running() is True

    def test_is_running_false_when_process_dead(self):
        """Should return False when process has exited."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            mock_process = MagicMock()
            mock_process.poll.return_value = 0  # 0 means process exited
            session._process = mock_process
            assert session.is_running() is False

    def test_start_creates_process(self):
        """Should start ttyd process on the port with session name."""
        mock_process = MagicMock()
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.ensure_tmux_session"):
                    with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process) as mock_start:
                        session = TerminalSession()
                        session.start()
                        mock_start.assert_called_once_with(8080, session_name="default")
                        assert session._process is mock_process

    def test_start_checks_ttyd_availability(self):
        """Should check ttyd is available before starting."""
        mock_process = MagicMock()
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=False):
                with patch("demorec.ttyd.find_ttyd") as mock_find:
                    with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                        session = TerminalSession()
                        session.start()
                        mock_find.assert_called_once()

    def test_start_is_idempotent_when_running(self):
        """Should not restart if already running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process) as mock_start:
                    session = TerminalSession()
                    session.start()
                    session.start()  # Second call should be no-op
                    mock_start.assert_called_once()

    def test_start_reassigns_port_when_restarting(self):
        """Should get a new port when restarting a dead session."""
        dead_process = MagicMock()
        dead_process.poll.return_value = 1  # Process died
        new_process = MagicMock()
        new_process.poll.return_value = None

        port_calls = [8080, 9090]  # First port, then new port

        with patch("demorec.modes.terminal.find_free_port", side_effect=port_calls):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd") as mock_start:
                    mock_start.side_effect = [dead_process, new_process]
                    session = TerminalSession()
                    assert session.port == 8080
                    session.start()  # First start
                    assert session._process is dead_process
                    # Simulate process death
                    dead_process.poll.return_value = 1
                    session.start()  # Restart - should get new port
                    assert session.port == 9090
                    assert mock_start.call_count == 2

    def test_stop_terminates_process(self):
        """Should terminate the ttyd process."""
        mock_process = MagicMock()
        mock_process.wait.return_value = None
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            session._process = mock_process
            session.stop()
            mock_process.terminate.assert_called_once()
            mock_process.wait.assert_called_once_with(timeout=2)
            assert session._process is None

    def test_stop_kills_on_timeout(self):
        """Should kill process if terminate times out."""
        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="ttyd", timeout=2)
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            session._process = mock_process
            session.stop()
            mock_process.kill.assert_called_once()

    def test_stop_handles_no_process(self):
        """Should handle stop when no process exists."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession()
            session.stop()  # Should not raise

    def test_repr_shows_status(self):
        """Should show running/stopped status in repr."""
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            session = TerminalSession("test")
            assert "stopped" in repr(session)
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            session._process = mock_process
            assert "running" in repr(session)


class TestTerminalSessionManager:
    """Test TerminalSessionManager class."""

    def test_get_or_create_creates_new_session(self):
        """Should create new session when name not found."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    session = manager.get_or_create("server")
                    assert session.name == "server"
                    assert len(manager) == 1

    def test_get_or_create_returns_existing_session(self):
        """Should return existing session when name matches."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    session1 = manager.get_or_create("server")
                    session2 = manager.get_or_create("server")
                    assert session1 is session2
                    assert len(manager) == 1

    def test_multiple_named_sessions_are_independent(self):
        """Should manage multiple independent sessions."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        ports = [8080, 8081, 8082]
        with patch("demorec.modes.terminal.find_free_port", side_effect=ports):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    server = manager.get_or_create("server")
                    client = manager.get_or_create("client")
                    default = manager.get_or_create("default")
                    assert server.name == "server"
                    assert client.name == "client"
                    assert default.name == "default"
                    assert len(manager) == 3
                    assert server.port != client.port
                    assert client.port != default.port

    def test_get_or_create_restarts_dead_session(self):
        """Should restart session if it died."""
        live_process = MagicMock()
        live_process.poll.return_value = None  # Running initially
        new_process = MagicMock()
        new_process.poll.return_value = None  # Running

        processes = [live_process, new_process]
        with patch("demorec.modes.terminal.find_free_port", side_effect=[8080, 9090]):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", side_effect=processes):
                    manager = TerminalSessionManager()
                    session1 = manager.get_or_create("server")
                    assert session1._process is live_process
                    assert session1.port == 8080
                    # Process dies
                    live_process.poll.return_value = 1  # Now dead
                    # Get same session - should restart with new port
                    session2 = manager.get_or_create("server")
                    assert session2 is session1  # Same object
                    assert session2._process is new_process
                    assert session2.port == 9090  # New port assigned

    def test_cleanup_stops_all_sessions(self):
        """Should stop all managed sessions on cleanup."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.return_value = None
        with patch("demorec.modes.terminal.find_free_port", side_effect=[8080, 8081]):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    manager.get_or_create("server")
                    manager.get_or_create("client")
                    manager.cleanup()
                    assert len(manager) == 0
                    # terminate should be called for each session
                    assert mock_process.terminate.call_count >= 2

    def test_cleanup_handles_empty_manager(self):
        """Should handle cleanup when no sessions exist."""
        manager = TerminalSessionManager()
        manager.cleanup()  # Should not raise
        assert len(manager) == 0

    def test_repr_lists_session_names(self):
        """Should list session names in repr."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        with patch("demorec.modes.terminal.find_free_port", side_effect=[8080, 8081]):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    manager.get_or_create("server")
                    manager.get_or_create("client")
                    r = repr(manager)
                    assert "server" in r
                    assert "client" in r

    def test_default_session_name(self):
        """Should use 'default' as session name when not specified."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    session = manager.get_or_create()
                    assert session.name == "default"


class TestSessionPersistenceAcrossModeSwitches:
    """Test session persistence across mode switches (Issue #4)."""

    def test_session_persists_same_port(self):
        """Session should maintain same port across multiple accesses."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Running
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    # First access (terminal mode)
                    session1 = manager.get_or_create("default")
                    port1 = session1.port
                    # Simulate mode switch and return (browser -> terminal)
                    session2 = manager.get_or_create("default")
                    port2 = session2.port
                    assert port1 == port2  # Same port means same session
                    assert session1 is session2

    def test_process_not_restarted_if_running(self):
        """Should not restart process if still running."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Running
        with patch("demorec.modes.terminal.find_free_port", return_value=8080):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process) as mock_start:
                    manager = TerminalSessionManager()
                    manager.get_or_create("default")
                    manager.get_or_create("default")
                    manager.get_or_create("default")
                    # start_ttyd called only once
                    mock_start.assert_called_once()


class TestPortUniqueness:
    """Test port uniqueness guarantees."""

    def test_different_sessions_get_different_ports(self):
        """Each new session should get a unique port."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        ports = [8080, 8081, 8082, 8083]
        with patch("demorec.modes.terminal.find_free_port", side_effect=ports):
            with patch("demorec.modes.terminal.check_ttyd", return_value=True):
                with patch("demorec.modes.terminal.start_ttyd", return_value=mock_process):
                    manager = TerminalSessionManager()
                    s1 = manager.get_or_create("a")
                    s2 = manager.get_or_create("b")
                    s3 = manager.get_or_create("c")
                    s4 = manager.get_or_create("d")
                    ports_used = {s1.port, s2.port, s3.port, s4.port}
                    assert len(ports_used) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
