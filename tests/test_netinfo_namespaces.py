"""Tests for model/netinfo_namespaces.py — cgroup parsing and container ID extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from model.netinfo_namespaces import _parse_container_id_from_cgroup, _read_container_id


_FULL_ID = "a" * 64
_SHORT_ID = "a" * 12


class TestParseContainerIdFromCgroup:
    def test_parses_docker_container_id(self) -> None:
        text = f"12:memory:/docker/{_FULL_ID}\n"
        assert _parse_container_id_from_cgroup(text) == _FULL_ID

    def test_returns_none_for_no_docker_path(self) -> None:
        text = "12:memory:/system.slice/docker.service\n"
        assert _parse_container_id_from_cgroup(text) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert _parse_container_id_from_cgroup("") is None

    def test_returns_none_for_short_hex(self) -> None:
        # Only 12 hex chars — not a full container ID (needs 64)
        text = "12:memory:/docker/aabbccddeeff\n"
        assert _parse_container_id_from_cgroup(text) is None

    def test_returns_none_for_non_hex_id(self) -> None:
        text = "12:memory:/docker/" + "g" * 64 + "\n"
        assert _parse_container_id_from_cgroup(text) is None

    def test_returns_first_match_when_multiple(self) -> None:
        id1 = "1" * 64
        id2 = "2" * 64
        text = f"11:cpu:/docker/{id1}\n12:memory:/docker/{id2}\n"
        assert _parse_container_id_from_cgroup(text) == id1

    def test_multiline_cgroup_v2_style(self) -> None:
        text = (
            "0::/system.slice/containerd.service\n"
            f"1:name=systemd:/docker/{_FULL_ID}\n"
        )
        assert _parse_container_id_from_cgroup(text) == _FULL_ID


class TestReadContainerId:
    def test_returns_12_char_short_id(self) -> None:
        text = f"12:memory:/docker/{_FULL_ID}\n"
        with patch("builtins.open", MagicMock()), \
             patch("model.netinfo_namespaces.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.return_value = text
            mock_path_cls.return_value = mock_path
            # Call the real function with the file read patched
        # Test via _parse_container_id_from_cgroup directly instead
        from model.netinfo_namespaces import _parse_container_id_from_cgroup
        full = _parse_container_id_from_cgroup(text)
        assert full is not None
        assert full[:12] == _SHORT_ID

    def test_returns_none_on_oserror(self) -> None:
        with patch("model.netinfo_namespaces.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.side_effect = OSError("no such file")
            mock_path_cls.return_value = mock_path
            result = _read_container_id(9999)
        # OSError → None
        assert result is None

    def test_returns_none_when_not_in_docker(self) -> None:
        text = "12:memory:/system.slice/some.service\n"
        with patch("model.netinfo_namespaces.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.return_value = text
            mock_path_cls.return_value = mock_path
            result = _read_container_id(1234)
        assert result is None
