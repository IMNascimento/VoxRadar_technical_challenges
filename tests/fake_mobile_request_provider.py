from __future__ import annotations

from collections.abc import Mapping

from kwai_collector.security.signature_provider import PreparedMobileRequest


class FakeMobileRequestProvider:
    """Provider sintético usado pelos testes de integração."""

    def __init__(
        self,
        *,
        query_fields: Mapping[str, str] | None = None,
        body_fields: Mapping[str, str] | None = None,
        header_fields: Mapping[str, str] | None = None,
    ) -> None:
        self.query_fields = dict(query_fields or {})
        self.body_fields = dict(body_fields or {})
        self.header_fields = dict(header_fields or {})

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        prepared_query = dict(query)
        prepared_body = dict(body)
        prepared_headers = dict(headers)

        prepared_query.update(self.query_fields)
        prepared_body.update(self.body_fields)
        prepared_headers.update(self.header_fields)

        prepared_query.setdefault(
            "llsid",
            "synthetic-session",
        )

        return PreparedMobileRequest(
            query=prepared_query,
            body=prepared_body,
            headers=prepared_headers,
        )
