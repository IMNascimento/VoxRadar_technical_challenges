from kwai_collector.parsers.ui_comments import parse_ui_comments_xml


def test_parse_ui_comments_xml_extrai_e_deduplica(tmp_path):
    xml = """
    <hierarchy>
        <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
            <node
                resource-id="com.kwai.video.basis_extension:id/name"
                text="Mateus"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/comment"
                text="Comentário de teste"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/tv_comment_like_count"
                text="1"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/created"
                text="09-09-2025"
            />
        </node>

        <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
            <node
                resource-id="com.kwai.video.basis_extension:id/name"
                text="Mateus"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/comment"
                text="Comentário de teste"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/tv_comment_like_count"
                text="1"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/created"
                text="09-09-2025"
            />
        </node>
    </hierarchy>
    """

    arquivo = tmp_path / "window.xml"
    arquivo.write_text(xml, encoding="utf-8")

    comentarios = parse_ui_comments_xml(
        arquivo_xml=arquivo,
        postagem_url="https://www.kwai.com/@teste/video/123",
    )

    assert len(comentarios) == 1

    comentario = comentarios[0]

    assert comentario.autor.usuario == "Mateus"
    assert comentario.texto == "Comentário de teste"
    assert comentario.curtidas == 1
    assert comentario.data is not None
    assert comentario.data.year == 2025
    assert comentario.data.month == 9
    assert comentario.data.day == 9
