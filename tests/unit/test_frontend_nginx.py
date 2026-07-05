from pathlib import Path


NGINX_CONF = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"


def test_frontend_nginx_defers_bot_dns_resolution():
    nginx_conf = NGINX_CONF.read_text(encoding="utf-8")

    assert "resolver 127.0.0.11" in nginx_conf
    assert "set $bot_upstream bot:8080;" in nginx_conf
    assert "proxy_pass http://bot:8080" not in nginx_conf
