from kwai_collector.clients import mobile_comment_client


def test_build_root_payload_primeira_pagina():
    payload = mobile_comment_client.build_root_payload(
        photo_id="123",
        user_id="456",
    )

    assert payload == {
        "photoId": "123",
        "user_id": "456",
        "order": "desc",
        "count": "10",
        "photoPageType": "0",
        "requestType": "3",
        "llsid": "",
        "isPreload": "false",
        "preloadSource": "",
    }

    assert "pcursor" not in payload
    assert "selectedRootCommentId" not in payload


def test_build_root_payload_com_pcursor():
    payload = mobile_comment_client.build_root_payload(
        photo_id="123",
        user_id="456",
        pcursor="cursor_2",
    )

    assert payload["photoId"] == "123"
    assert payload["user_id"] == "456"
    assert payload["pcursor"] == "cursor_2"
    assert payload["count"] == "10"


def test_build_root_payload_com_selected_root_comment():
    payload = mobile_comment_client.build_root_payload(
        photo_id="123",
        user_id="456",
        selected_root_comment_id="999",
    )

    assert payload["selectedRootCommentId"] == "999"


def test_build_root_payload_count_minimo_10():
    payload = mobile_comment_client.build_root_payload(
        photo_id="123",
        user_id="456",
        count=3,
    )

    assert payload["count"] == "10"


def test_build_root_payload_count_maior_que_10():
    payload = mobile_comment_client.build_root_payload(
        photo_id="123",
        user_id="456",
        count=25,
    )

    assert payload["count"] == "25"


def test_build_subcomment_payload_primeira_pagina():
    payload = mobile_comment_client.build_subcomment_payload(
        photo_id="123",
        user_id="456",
        root_comment_id="789",
    )

    assert payload["photoId"] == "123"
    assert payload["user_id"] == "456"
    assert payload["rootCommentId"] == "789"
    assert "pcursor" not in payload
    assert payload["count"] == "3"
    assert payload["repeatCommentIds"] == ""


def test_build_subcomment_payload_com_repetidos():
    payload = mobile_comment_client.build_subcomment_payload(
        photo_id="123",
        user_id="456",
        root_comment_id="789",
        pcursor="cursor_2",
        count=10,
        repeat_comment_ids=["1", "2", "3"],
    )

    assert payload["pcursor"] == "cursor_2"
    assert payload["count"] == "10"
    assert payload["repeatCommentIds"] == "1,2,3"


def test_get_root_comments():
    data = {
        "rootComments": [
            {"comment_id": "1"},
            {"comment_id": "2"},
        ]
    }

    comments = mobile_comment_client.get_root_comments(data)

    assert len(comments) == 2
    assert comments[0]["comment_id"] == "1"


def test_get_subcomments():
    data = {
        "subComments": [
            {"comment_id": "10"},
        ]
    }

    comments = mobile_comment_client.get_subcomments(data)

    assert len(comments) == 1
    assert comments[0]["comment_id"] == "10"


def test_get_pcursor():
    assert mobile_comment_client.get_pcursor({"pcursor": "cursor_123"}) == "cursor_123"

    assert mobile_comment_client.get_pcursor({}) is None


def test_end_cursors():
    assert mobile_comment_client.is_end_cursor(None)
    assert mobile_comment_client.is_end_cursor("")
    assert mobile_comment_client.is_end_cursor("no_more")
    assert mobile_comment_client.is_end_cursor("more_cursor_total")

    assert not mobile_comment_client.is_end_cursor("cursor_123")


def test_collect_root_pages_com_paginacao():
    pages = [
        {
            "rootComments": [
                {"comment_id": "1"},
                {"comment_id": "2"},
            ],
            "pcursor": "cursor_1",
        },
        {
            "rootComments": [
                {"comment_id": "2"},
                {"comment_id": "3"},
            ],
            "pcursor": "cursor_2",
        },
        {
            "rootComments": [
                {"comment_id": "4"},
            ],
            "pcursor": "no_more",
        },
    ]

    comments = mobile_comment_client.collect_root_pages(pages)

    assert [item["comment_id"] for item in comments] == [
        "1",
        "2",
        "3",
        "4",
    ]


def test_collect_root_pages_para_em_cursor_repetido():
    pages = [
        {
            "rootComments": [
                {"comment_id": "1"},
            ],
            "pcursor": "cursor_1",
        },
        {
            "rootComments": [
                {"comment_id": "2"},
            ],
            "pcursor": "cursor_1",
        },
        {
            "rootComments": [
                {"comment_id": "3"},
            ],
            "pcursor": "cursor_2",
        },
    ]

    comments = mobile_comment_client.collect_root_pages(pages)

    assert [item["comment_id"] for item in comments] == [
        "1",
        "2",
    ]


def test_collect_subcomment_pages():
    embedded = [
        {"comment_id": "10"},
    ]

    pages = [
        {
            "subComments": [
                {"comment_id": "10"},
                {"comment_id": "11"},
            ],
            "pcursor": "cursor_sub_1",
        },
        {
            "subComments": [
                {"comment_id": "12"},
            ],
            "pcursor": "more_cursor_total",
        },
    ]

    comments = mobile_comment_client.collect_subcomment_pages(
        pages,
        embedded=embedded,
    )

    assert [item["comment_id"] for item in comments] == [
        "10",
        "11",
        "12",
    ]


def test_collect_subcomment_pages_respeita_limite():
    pages = [
        {
            "subComments": [
                {"comment_id": "20"},
                {"comment_id": "21"},
                {"comment_id": "22"},
            ],
            "pcursor": "cursor_sub_1",
        }
    ]

    comments = mobile_comment_client.collect_subcomment_pages(
        pages,
        max_subcomments=2,
    )

    assert len(comments) == 2
    assert comments[0]["comment_id"] == "20"
    assert comments[1]["comment_id"] == "21"
