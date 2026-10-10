from pathlib import Path

from kwai_collector.providers.adb_comment_provider import AdbCommentProvider


def test_adb_comment_provider_extrai_e_deduplica_comentarios(
    monkeypatch,
    tmp_path: Path,
) -> None:
    arquivo_xml = tmp_path / "window.xml"
    video_xml = tmp_path / "video.xml"

    provider = AdbCommentProvider(
        arquivo_xml=arquivo_xml,
        video_xml=video_xml,
    )

    chamadas: list[str] = []
    captura_atual = 0

    xmls = [
        """
        <hierarchy>
            <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
                <node
                    resource-id="com.kwai.video.basis:id/name"
                    text="Usuario 1"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/comment"
                    text="Comentario 1"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/created"
                    text="09-09-2025"
                />
            </node>

            <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
                <node
                    resource-id="com.kwai.video.basis:id/name"
                    text="Usuario 2"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/comment"
                    text="Comentario 2"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/tv_comment_like_count"
                    text="5"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/created"
                    text="08-09-2025"
                />
            </node>
        </hierarchy>
        """,
        """
        <hierarchy>
            <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
                <node
                    resource-id="com.kwai.video.basis:id/name"
                    text="Usuario 2"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/comment"
                    text="Comentario 2"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/tv_comment_like_count"
                    text="5"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/created"
                    text="08-09-2025"
                />
            </node>

            <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
                <node
                    resource-id="com.kwai.video.basis:id/name"
                    text="Usuario 3"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/comment"
                    text="Comentario 3"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/created"
                    text="07-09-2025"
                />
            </node>
        </hierarchy>
        """,
        """
        <hierarchy>
            <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
                <node
                    resource-id="com.kwai.video.basis:id/name"
                    text="Usuario 3"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/comment"
                    text="Comentario 3"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/created"
                    text="07-09-2025"
                />
            </node>
        </hierarchy>
        """,
        """
        <hierarchy>
            <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
                <node
                    resource-id="com.kwai.video.basis:id/name"
                    text="Usuario 3"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/comment"
                    text="Comentario 3"
                />
                <node
                    resource-id="com.kwai.video.basis_extension:id/created"
                    text="07-09-2025"
                />
            </node>
        </hierarchy>
        """,
    ]

    def fake_abrir_post(postagem_url: str) -> None:
        chamadas.append(f"post:{postagem_url}")

    def fake_abrir_comentarios() -> None:
        chamadas.append("comentarios")

    def fake_rolar_comentarios() -> None:
        chamadas.append("scroll")

    def fake_capturar_xml(
        arquivo_remoto: str,
        arquivo_local: Path,
    ) -> None:
        nonlocal captura_atual

        chamadas.append(f"xml:{arquivo_remoto}")

        arquivo_local.write_text(
            xmls[captura_atual],
            encoding="utf-8",
        )

        captura_atual += 1

    monkeypatch.setattr(
        provider,
        "_abrir_post",
        fake_abrir_post,
    )

    monkeypatch.setattr(
        provider,
        "_abrir_comentarios",
        fake_abrir_comentarios,
    )

    monkeypatch.setattr(
        provider,
        "_rolar_comentarios",
        fake_rolar_comentarios,
    )

    monkeypatch.setattr(
        provider,
        "_capturar_xml",
        fake_capturar_xml,
    )

    monkeypatch.setattr(
        "kwai_collector.providers.adb_comment_provider.time.sleep",
        lambda _: None,
    )

    url = "https://www.kwai.com/@teste/video/123"

    comentarios = provider.get_comments(url)

    assert len(comentarios) == 3

    assert comentarios[0].autor.usuario == "Usuario 1"
    assert comentarios[1].autor.usuario == "Usuario 2"
    assert comentarios[2].autor.usuario == "Usuario 3"

    assert comentarios[1].curtidas == 5

    assert chamadas == [
        f"post:{url}",
        "comentarios",
        "xml:/sdcard/window.xml",
        "scroll",
        "xml:/sdcard/window.xml",
        "scroll",
        "xml:/sdcard/window.xml",
        "scroll",
        "xml:/sdcard/window.xml",
    ]
