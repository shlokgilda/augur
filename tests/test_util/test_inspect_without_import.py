"""
Tests for the inspect_without_import module.

Every test calls get_phase_names_without_import() rather than doing
inline AST walks, so we're actually exercising the real function.
"""

import os
import tempfile
from pathlib import Path

import pytest
from augur.util.inspect_without_import import get_phase_names_without_import


def _write_temp_file(code: str) -> Path:
    """Write code to a temp file and return its Path.

    Args:
        code: Python source code to write to the file.

    Returns:
        Path to the created temp file.
    """
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
    f.write(code)
    f.close()
    return Path(f.name)


class TestGetPhaseNamesWithoutImport:
    """Tests for the main function logic."""

    def test_extracts_actual_phase_names(self):
        """Checks if we can actually pull the real phase names from start_tasks.py."""
        phase_names = get_phase_names_without_import()

        assert isinstance(phase_names, list)
        assert len(phase_names) > 0

        for name in phase_names:
            assert '_phase' in name, f"Function {name} doesn't seem to be a phase function."

        # These are the outputs of the original version of the function as of 7a46497aaed6c6dbecce9a1f8dda58282f9dd9fe
        expected_phases = [
            'prelim_phase',
            'primary_repo_collect_phase',
            'secondary_repo_collect_phase'
        ]

        for expected in expected_phases:
            assert expected in phase_names, f"We missed a required phase: '{expected}'"

        for actual in phase_names:
            assert actual in expected_phases, f"We have an extra phase: '{actual}'"

    def test_mixed_phase_and_non_phase_functions(self):
        """Only functions whose names end with '_phase' should be returned."""
        code = '''\
def prelim_phase():
    pass

def helper_function():
    pass

def secondary_collect_phase():
    pass

def not_a_phase_at_all():
    pass
'''
        path = _write_temp_file(code)
        try:
            result = get_phase_names_without_import(source_path=path)
            assert result == ['prelim_phase', 'secondary_collect_phase']
        finally:
            os.unlink(path)

    def test_ignores_non_phase_functions(self):
        """Functions with '_phase' mid-name but not at the end should be ignored."""
        code = '''\
def some_phase():
    pass

def build_primary_phase_request():
    pass

def unrelated_function():
    pass
'''
        path = _write_temp_file(code)
        try:
            result = get_phase_names_without_import(source_path=path)
            assert 'some_phase' in result
            assert 'build_primary_phase_request' not in result
            assert 'unrelated_function' not in result
            assert len(result) == 1
        finally:
            os.unlink(path)

    def test_handles_async_functions(self):
        """Async functions ending with '_phase' should be detected."""
        code = '''\
async def async_phase():
    pass

def sync_phase():
    pass
'''
        path = _write_temp_file(code)
        try:
            result = get_phase_names_without_import(source_path=path)
            assert 'async_phase' in result
            assert 'sync_phase' in result
            assert len(result) == 2
        finally:
            os.unlink(path)

    def test_ignores_variables_with_matching_name(self):
        """Variables with '_phase' in their name should NOT be picked up."""
        code = '''\
this_is_a_variable_phase = 1

def actual_function_phase():
    pass
'''
        path = _write_temp_file(code)
        try:
            result = get_phase_names_without_import(source_path=path)
            assert result == ['actual_function_phase']
        finally:
            os.unlink(path)

    def test_returns_list_of_strings(self):
        """Sanity check: we should always get back a list of strings."""
        phase_names = get_phase_names_without_import()

        assert isinstance(phase_names, list)
        for name in phase_names:
            assert isinstance(name, str)

    def test_no_duplicates(self):
        """Ensures we don't accidentally return the same function twice."""
        phase_names = get_phase_names_without_import()

        assert len(phase_names) == len(set(phase_names)), \
            f"Found duplicates: {phase_names}"


class TestEdgeCases:
    """Edge cases for the phase name extraction."""

    def test_empty_file(self):
        """An empty file should return an empty list."""
        path = _write_temp_file('')
        try:
            result = get_phase_names_without_import(source_path=path)
            assert result == []
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        """A missing file should raise FileNotFoundError."""
        fake_path = Path('/tmp/nonexistent_file_abc123.py')
        with pytest.raises(FileNotFoundError):
            get_phase_names_without_import(source_path=fake_path)
