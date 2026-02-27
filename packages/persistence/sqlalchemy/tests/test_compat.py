"""Tests for compatibility utilities."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_sqlalchemy.compat import (
    HAS_ADVANCED,
    HAS_GEOMETRY,
    HAS_PYDANTIC_SHAPELY,
    require_advanced,
    require_geometry,
)


class TestModuleFlags:
    """Tests for module availability flags."""

    def test_has_advanced_is_bool(self):
        """Test HAS_ADVANCED is a boolean."""
        assert isinstance(HAS_ADVANCED, bool)

    def test_has_geometry_is_bool(self):
        """Test HAS_GEOMETRY is a boolean."""
        assert isinstance(HAS_GEOMETRY, bool)

    def test_has_pydantic_shapely_is_bool(self):
        """Test HAS_PYDANTIC_SHAPELY is a boolean."""
        assert isinstance(HAS_PYDANTIC_SHAPELY, bool)


class TestRequireAdvanced:
    """Tests for require_advanced function."""

    def test_require_advanced_when_available(self):
        """Test require_advanced does not raise when advanced-core is available."""
        if HAS_ADVANCED:
            # Should not raise
            require_advanced("test-feature")
        else:
            pytest.skip("cqrs-ddd-advanced-core not installed")

    def test_require_advanced_when_not_available(self):
        """Test require_advanced raises ImportError when advanced-core is not available."""
        if not HAS_ADVANCED:
            with pytest.raises(ImportError) as exc_info:
                require_advanced("test-feature")

            error_msg = str(exc_info.value)
            assert "test-feature" in error_msg
            assert "cqrs-ddd-advanced-core" in error_msg
            assert "pip install" in error_msg
        else:
            pytest.skip("cqrs-ddd-advanced-core is installed")

    def test_require_advanced_error_message_format(self):
        """Test require_advanced error message format."""
        if not HAS_ADVANCED:
            with pytest.raises(
                ImportError, match="test-feature requires.*advanced-core"
            ):
                require_advanced("test-feature")
        else:
            pytest.skip("cqrs-ddd-advanced-core is installed")


class TestRequireGeometry:
    """Tests for require_geometry function."""

    def test_require_geometry_when_available(self):
        """Test require_geometry does not raise when geoalchemy2 is available."""
        if HAS_GEOMETRY:
            # Should not raise
            require_geometry("test-feature")
        else:
            pytest.skip("geoalchemy2 not installed")

    def test_require_geometry_when_not_available(self):
        """Test require_geometry raises ImportError when geoalchemy2 is not available."""
        if not HAS_GEOMETRY:
            with pytest.raises(ImportError) as exc_info:
                require_geometry("test-feature")

            error_msg = str(exc_info.value)
            assert "test-feature" in error_msg
            assert "geoalchemy2" in error_msg
            assert "pip install" in error_msg
        else:
            pytest.skip("geoalchemy2 is installed")

    def test_require_geometry_error_message_format(self):
        """Test require_geometry error message format."""
        if not HAS_GEOMETRY:
            with pytest.raises(ImportError, match="test-feature requires.*geoalchemy2"):
                require_geometry("test-feature")
        else:
            pytest.skip("geoalchemy2 is installed")


class TestImportGuards:
    """Tests that import guards are set correctly."""

    def test_advanced_guard_reflects_import_status(self):
        """Test HAS_ADVANCED reflects actual import status."""
        # If HAS_ADVANCED is True, we should be able to import
        if HAS_ADVANCED:
            import cqrs_ddd_advanced_core  # noqa: F401

            assert True
        else:
            # If False, import should fail
            with pytest.raises(ImportError):
                import cqrs_ddd_advanced_core  # noqa: F401

    def test_geometry_guard_reflects_import_status(self):
        """Test HAS_GEOMETRY reflects actual import status."""
        # If HAS_GEOMETRY is True, we should be able to import
        if HAS_GEOMETRY:
            import geoalchemy2  # noqa: F401

            assert True
        else:
            # If False, import should fail
            with pytest.raises(ImportError):
                import geoalchemy2  # noqa: F401

    def test_pydantic_shapely_guard_reflects_import_status(self):
        """Test HAS_PYDANTIC_SHAPELY reflects actual import status."""
        # If HAS_PYDANTIC_SHAPELY is True, we should be able to import
        if HAS_PYDANTIC_SHAPELY:
            import pydantic_shapely  # noqa: F401

            assert True
        else:
            # If False, import should fail
            with pytest.raises(ImportError):
                import pydantic_shapely  # noqa: F401


class TestMultipleFeatures:
    """Tests using multiple features together."""

    def test_require_all_available_features(self):
        """Test requiring all features that are available."""
        if HAS_ADVANCED:
            require_advanced("feature1")
        if HAS_GEOMETRY:
            require_geometry("feature2")

        # If we get here, all available features passed
        assert True

    def test_feature_names_in_error_messages(self):
        """Test that feature names appear in error messages."""
        if not HAS_ADVANCED:
            with pytest.raises(ImportError, match="my-custom-feature"):
                require_advanced("my-custom-feature")
        else:
            pytest.skip("cqrs-ddd-advanced-core is installed")

    def test_different_feature_names(self):
        """Test that different feature names appear in error messages."""
        if not HAS_ADVANCED:
            with pytest.raises(ImportError, match="aggregate-snapshot"):
                require_advanced("aggregate-snapshot")
        else:
            pytest.skip("cqrs-ddd-advanced-core is installed")

        if not HAS_GEOMETRY:
            with pytest.raises(ImportError, match="spatial-query"):
                require_geometry("spatial-query")
        else:
            pytest.skip("geoalchemy2 is installed")
