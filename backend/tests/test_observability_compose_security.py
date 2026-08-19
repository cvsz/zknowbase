from pathlib import Path


def test_observability_profile_disables_anonymous_grafana_and_requires_admin_secret():
    compose = (Path(__file__).parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    grafana = compose.split("\n  grafana:\n", 1)[1].split("\n  backend:\n", 1)[0]

    assert 'GF_AUTH_ANONYMOUS_ENABLED: "false"' in grafana
    assert "GF_AUTH_ANONYMOUS_ORG_ROLE" not in grafana
    assert "GF_USERS_ALLOW_SIGN_UP" in grafana
    assert "GF_SECURITY_ADMIN_PASSWORD: ${ZKB_GRAFANA_ADMIN_PASSWORD:?" in grafana
    assert "127.0.0.1:3001:3000" in grafana
