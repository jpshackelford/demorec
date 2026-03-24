"""Unit tests for ttyd process management utilities.

Tests cover:
- find_free_port: Port allocation
- check_ttyd: Executable availability checking
- make_clean_env: Environment preparation
- _build_ttyd_cmd: Command line building
- _ttyd_not_found_msg: Error message generation
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from demorec.ttyd import (
    find_free_port,
    check_ttyd,
    make_clean_env,
    _build_ttyd_cmd,
    _ttyd_not_found_msg,
    _search_ttyd_path,
    stop_ttyd,
)


class TestFindFreePort:
    """Test find_free_port function."""

    def test_returns_valid_port(self):
        """Should return a valid port number."""
        port = find_free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_returns_different_ports(self):
        """Should return different ports on subsequent calls."""
        ports = [find_free_port() for _ in range(5)]
        # Ports should be unique (with high probability)
        assert len(set(ports)) >= 3  # Allow some duplicates due to timing


class TestCheckTtyd:
    """Test check_ttyd function."""

    def test_returns_true_when_ttyd_available(self):
        """Should return True when ttyd is found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert check_ttyd() is True

    def test_returns_false_when_ttyd_not_found(self):
        """Should return False when ttyd is not in PATH."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert check_ttyd() is False

    def test_returns_false_when_ttyd_fails(self):
        """Should return False when ttyd returns non-zero."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert check_ttyd() is False


class TestMakeCleanEnv:
    """Test make_clean_env function."""

    def test_sets_term(self):
        """Should set TERM to xterm-256color."""
        env = make_clean_env()
        assert env["TERM"] == "xterm-256color"

    def test_sets_simple_ps1(self):
        """Should set PS1 to simple prompt."""
        env = make_clean_env()
        assert env["PS1"] == "$ "

    def test_clears_prompt_command(self):
        """Should clear PROMPT_COMMAND."""
        env = make_clean_env()
        assert env["PROMPT_COMMAND"] == ""

    def test_removes_prompt_variables(self):
        """Should remove variables containing 'PROMPT' (except PROMPT_COMMAND)."""
        with patch.dict(os.environ, {"FANCY_PROMPT": "foo", "PROMPT_CUSTOM": "bar"}):
            env = make_clean_env()
            assert "FANCY_PROMPT" not in env
            assert "PROMPT_CUSTOM" not in env

    def test_preserves_other_env_vars(self):
        """Should preserve non-prompt environment variables."""
        with patch.dict(os.environ, {"HOME": "/home/test", "USER": "testuser"}):
            env = make_clean_env()
            assert "HOME" in env
            assert "USER" in env

    def test_adds_local_bin_to_path(self):
        """Should add ~/.local/bin to PATH if not present."""
        from pathlib import Path

        local_bin = str(Path.home() / ".local/bin")
        # Temporarily set PATH without local_bin
        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
            env = make_clean_env()
            assert local_bin in env["PATH"]


class TestBuildTtydCmd:
    """Test _build_ttyd_cmd function."""

    def test_includes_port(self):
        """Should include port argument."""
        cmd = _build_ttyd_cmd("/usr/bin/ttyd", 8080)
        assert "-p" in cmd
        assert "8080" in cmd

    def test_includes_writable_flag(self):
        """Should include --writable flag."""
        cmd = _build_ttyd_cmd("/usr/bin/ttyd", 8080)
        assert "--writable" in cmd

    def test_includes_once_flag(self):
        """Should include --once flag."""
        cmd = _build_ttyd_cmd("/usr/bin/ttyd", 8080)
        assert "--once" in cmd

    def test_includes_bash_with_options(self):
        """Should include bash with --norc and --noprofile."""
        cmd = _build_ttyd_cmd("/usr/bin/ttyd", 8080)
        assert "/bin/bash" in cmd
        assert "--norc" in cmd
        assert "--noprofile" in cmd

    def test_starts_with_ttyd_path(self):
        """Should start with the ttyd path."""
        cmd = _build_ttyd_cmd("/custom/path/ttyd", 9090)
        assert cmd[0] == "/custom/path/ttyd"


class TestTtydNotFoundMsg:
    """Test _ttyd_not_found_msg function."""

    def test_includes_install_instructions(self):
        """Should include installation instructions."""
        msg = _ttyd_not_found_msg()
        assert "ttyd" in msg
        assert "wget" in msg or "Install" in msg

    def test_returns_string(self):
        """Should return a non-empty string."""
        msg = _ttyd_not_found_msg()
        assert isinstance(msg, str)
        assert len(msg) > 20


class TestSearchTtydPath:
    """Test _search_ttyd_path function."""

    def test_returns_path_when_found_in_which(self):
        """Should return path when shutil.which finds ttyd."""
        with patch("shutil.which", return_value="/usr/local/bin/ttyd"):
            path = _search_ttyd_path()
            assert path == "/usr/local/bin/ttyd"

    def test_returns_none_when_not_found(self):
        """Should return None when ttyd is not found."""
        with patch("shutil.which", return_value=None):
            with patch("pathlib.Path.exists", return_value=False):
                path = _search_ttyd_path()
                assert path is None


class TestStopTtyd:
    """Test stop_ttyd function."""

    def test_handles_none_process(self):
        """Should handle None process gracefully."""
        # Should not raise
        stop_ttyd(None)

    def test_terminates_process(self):
        """Should call terminate on process."""
        mock_process = MagicMock()
        mock_process.wait.return_value = None
        stop_ttyd(mock_process)
        mock_process.terminate.assert_called_once()

    def test_waits_for_process(self):
        """Should wait for process to terminate."""
        mock_process = MagicMock()
        mock_process.wait.return_value = None
        stop_ttyd(mock_process)
        mock_process.wait.assert_called_once_with(timeout=2)

    def test_kills_on_timeout(self):
        """Should kill process if it doesn't terminate in time."""
        import subprocess

        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="ttyd", timeout=2)
        stop_ttyd(mock_process)
        mock_process.kill.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
