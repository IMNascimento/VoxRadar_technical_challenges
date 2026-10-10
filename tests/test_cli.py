import json
from urllib.parse import parse_qs

import httpx
import respx
from typer.testing import CliRunner

from kwai_collector import scraper
from kwai_collector.cli import app
from kwai_collector.client import MOBILE_HOSTS, WEB_URL
from tests.conftest import load

runner = CliRunner()
HOST = MOBILE_HOSTS[0]
POST_URL = "https://www.kwai.com/@ajudantedoreid/video/5210251923800764971"
END = {"result": 1, "pcursor": "no_more"}


def form(request):
    return {k: v[0] for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()}


@respx.mock
def test_search(tmp_path):
    respx.post(WEB_URL + scraper.SEARCH_PATH).mock(
        return_value=httpx.Response(200, json=load("search_response.json"))
    )
    out = tmp_path / "busca.json"

    result = runner.invoke(app, ["search", "-k", "sports", "-l", "2", "-o", str(out)])

    assert result.exit_code == 0
    posts = json.loads(out.read_text(encoding="utf-8"))
    assert len(posts) == 2
    assert posts[0]["url"].startswith("https://www.kwai.com/@")


@respx.mock
def test_search_pagina_ate_nao_vir_post_novo():
    feeds = load("search_response.json")["feeds"]
    route = respx.post(WEB_URL + scraper.SEARCH_PATH).mock(
        side_effect=[
            httpx.Response(200, json={"result": 1, "feeds": feeds[:2]}),
            httpx.Response(200, json={"result": 1, "feeds": feeds[2:]}),
            httpx.Response(200, json={"result": 1, "feeds": feeds}),
        ]
    )

    result = runner.invoke(app, ["search", "-k", "sports", "-l", "10"])

    assert result.exit_code == 0
    assert len(json.loads(result.stdout)) == 3
    sent = [json.loads(call.request.content) for call in route.calls]
    assert [(body["pcursor"], body["count"]) for body in sent] == [(0, 10), (10, 10), (20, 10)]


@respx.mock
def test_profile():
    respx.post(HOST + scraper.USER_INFO_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "users": [{"user_id": 150001752740839}]}
        )
    )
    feed = respx.post(HOST + scraper.PROFILE_PATH).mock(
        side_effect=[
            httpx.Response(200, json=load("mobile_profile.json")),
            httpx.Response(200, json=END),
        ]
    )

    result = runner.invoke(app, ["profile", "-u", "@puratabela"])

    assert result.exit_code == 0
    posts = json.loads(result.stdout)
    assert [p["id"] for p in posts] == ["5239243853418407006", "5213066681976934238"]
    assert form(feed.calls[0].request)["user_id"] == "150001752740839"


@respx.mock
def test_comments_com_respostas():
    pages = load("mobile_comments.json")
    respx.post(HOST + scraper.COMMENTS_PATH).mock(
        side_effect=[httpx.Response(200, json=pages[0]), httpx.Response(200, json=END)]
    )

    def replies(request):
        if form(request)["rootCommentId"] == "155133451079517322" and not form(request)["pcursor"]:
            return httpx.Response(200, json=load("mobile_replies.json"))
        return httpx.Response(200, json=END)

    respx.post(HOST + scraper.REPLIES_PATH).mock(side_effect=replies)

    result = runner.invoke(app, ["comments", "--url", POST_URL, "--with-replies"])

    assert result.exit_code == 0
    items = json.loads(result.stdout)
    assert len(items) == 5  # 2 raízes + 3 respostas da primeira
    assert items[0]["respostas_total"] == 59
    assert items[1]["parent_id"] == "155133451079517322"
    assert items[1]["reply_to_usuario"] == "Gonzaga da fz 25"


def test_url_invalida_sai_com_2():
    result = runner.invoke(app, ["comments", "--url", "https://www.kwai.com/@a"])
    assert result.exit_code == 2


@respx.mock
def test_erro_de_rede_sai_com_1():
    respx.post(WEB_URL + scraper.SEARCH_PATH).mock(side_effect=httpx.ConnectError("sem rede"))
    result = runner.invoke(app, ["search", "-k", "sports"])
    assert result.exit_code == 1
