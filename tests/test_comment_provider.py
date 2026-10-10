from kwai_collector.providers.comment_provider import XmlCommentProvider


def test_xml_comment_provider_retorna_comentarios(tmp_path):
    xml = """
    <hierarchy>
        <node resource-id="com.kwai.video.basis_extension:id/comment_frame">
            <node
                resource-id="com.kwai.video.basis_extension:id/name"
                text="Usuario Teste"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/comment"
                text="Comentario de teste"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/tv_comment_like_count"
                text="5"
            />
            <node
                resource-id="com.kwai.video.basis_extension:id/created"
                text="09-09-2025"
            />
        </node>
    </hierarchy>
    """

    arquivo_xml = tmp_path / "window.xml"
    arquivo_xml.write_text(xml, encoding="utf-8")

    provider = XmlCommentProvider(
        arquivo_xml=arquivo_xml,
    )

    comentarios = provider.get_comments(
        postagem_url="https://www.kwai.com/@teste/video/123",
    )

    assert len(comentarios) == 1
    assert comentarios[0].autor.usuario == "Usuario Teste"
    assert comentarios[0].texto == "Comentario de teste"
    assert comentarios[0].curtidas == 5
