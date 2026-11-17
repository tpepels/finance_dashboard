"""POST is allowed only as a declared, read-only GraphQL query to one path.

Vanguard serves UCITS fund holdings only through a GraphQL endpoint that
does not answer GET. Every other policy stays GET/HEAD only.
"""
import json
import unittest

import httpx

from finance_dashboard.source_policy import managed_client
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.source_policy_types import PolicyViolation

from test_source_policy import PolicyHarness

URL = "https://www.de.vanguard/gpx/graphql"
QUERY = 'query FundsQuery($portIds: [String!]!) { funds(portIds: $portIds) { portId } }'


class GraphqlReadPolicyTests(PolicyHarness):
    def post(self, url, body, *, content_type="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        with managed_client(policy_gate=self.gate(),
                            transport=httpx.MockTransport(lambda r: httpx.Response(200))) as client:
            return client.post(url, content=payload, headers={"Content-Type": content_type})

    def test_declared_read_only_query_is_permitted(self):
        response = self.post(URL, {"operationName": "FundsQuery", "query": QUERY,
                                   "variables": {"portIds": ["9679"]}})
        self.assertEqual(response.status_code, 200)

    def test_mutation_other_path_large_body_or_non_json_is_refused(self):
        cases = [
            (URL, {"query": "mutation Save { save { id } }"}),
            (URL, {"query": QUERY + " mutation X { y }"}),
            ("https://www.de.vanguard/gpx/other", {"query": QUERY}),
            (URL, {"query": QUERY, "variables": {"pad": "x" * 20000}}),
            (URL, {"variables": {}}),
        ]
        for url, body in cases:
            with self.subTest(url=url, body=str(body)[:40]):
                self.clock.advance(3600)
                with self.assertRaises(PolicyViolation):
                    self.post(url, body)
        self.clock.advance(3600)
        with self.assertRaises(PolicyViolation):
            self.post(URL, b"query { funds }", content_type="text/plain")

    def test_post_stays_refused_for_every_other_publisher(self):
        with self.assertRaises(PolicyViolation):
            self.managed_request("POST", "https://www.ishares.com/uk/individual/en/products/253743/")

    def test_post_method_without_a_declared_read_only_path_is_invalid(self):
        raw = json.loads(self.catalog.read_text())
        for row in raw["policies"]:
            if row["id"] == "vanguard-de":
                row["restrictions"].pop("read_only_graphql_post")
        self.catalog.write_text(json.dumps(raw))
        with self.assertRaises(PolicyViolation) as error:
            PolicyRegistry(self.catalog)
        self.assertEqual(error.exception.reason, "invalid_restrictions")


if __name__ == "__main__":
    unittest.main()
