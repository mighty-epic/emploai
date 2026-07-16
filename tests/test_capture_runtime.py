from __future__ import annotations

from app_backend.capture_runtime import _capture_backend_error


def test_windows_bitblt_access_error_explains_rdp_recovery():
    error = _capture_backend_error(
        RuntimeError("Windows graphics function failed: BitBlt: Access is denied."),
        platform_name="nt",
    )

    assert "interactive display cannot be captured" in str(error)
    assert "Restore and unlock" in str(error)
    assert "minimized" in str(error)


def test_other_capture_errors_keep_their_specific_detail():
    error = _capture_backend_error(RuntimeError("monitor not found"), platform_name="posix")
    assert str(error) == "monitor not found"
