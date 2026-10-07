from mac_converter.help_content import TOOL_HELP
from mac_converter.network import check_wildcard, lookup_routes


def test_help_covers_all_tools_and_promises_no_full_route_acl_simulation():
    assert [topic.name for topic in TOOL_HELP] == [
        "MAC",
        "IPv4",
        "MTU / MSS",
        "Маршруты",
        "ACL",
        "Пароли",
    ]
    assert all(
        topic.purpose and topic.steps and topic.example and topic.limits for topic in TOOL_HELP
    )
    assert "permit/deny" in TOOL_HELP[4].limits
    assert "метрики" in TOOL_HELP[3].limits
    assert "История" in TOOL_HELP[5].limits


def test_documented_acl_and_route_examples_are_true():
    assert check_wildcard("192.168.1.0", "0.0.0.255", "192.168.1.42").matches
    assert not check_wildcard("192.168.1.0", "0.0.0.255", "192.168.2.42").matches
    assert check_wildcard("10.10.0.0", "0.0.255.254", "10.10.5.2").matches
    assert not check_wildcard("10.10.0.0", "0.0.255.254", "10.10.5.3").matches
    result = lookup_routes(
        "10.20.30.40", "0.0.0.0/0 default\n10.20.0.0/16 core\n10.20.30.0/24 access"
    )
    assert "[LPM] 10.20.30.0/24" in result.copy_text()
