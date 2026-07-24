from app_backend.fleet_presence import desktop_presence_status


def test_recent_connected_desktop_stays_connected():
    assert desktop_presence_status("connected", 970.0, now=1_000.0) == "connected"


def test_connected_desktop_without_a_recent_heartbeat_is_offline():
    assert desktop_presence_status("connected", 939.0, now=1_000.0) == "offline"
    assert desktop_presence_status("online", None, now=1_000.0) == "offline"


def test_explicit_non_connected_state_is_preserved():
    assert desktop_presence_status("planned", 1.0, now=1_000.0) == "planned"

