import unittest

from ottv2_runner.errors import InfrastructureError
from ottv2_runner.registry import DockerRegistryPublisher

DIGEST = "sha256:" + "a" * 64


class FakeImage:
    def __init__(self, tags):
        self.tags = tags

    def tag(self, repository, tag):
        self.tags.append((repository, tag))


class FakeImages:
    def __init__(self, records):
        self.records = records
        self.tags = []

    def get(self, image_id):
        return FakeImage(self.tags)

    def push(self, repository, tag, stream, decode):
        return iter(self.records)


class FakeClient:
    def __init__(self, records):
        self.images = FakeImages(records)


class RegistryPublisherTests(unittest.TestCase):
    def test_returns_immutable_reference_from_status_digest(self):
        client = FakeClient([{"status": f"sub: digest: {DIGEST} size: 1616"}])
        publisher = DockerRegistryPublisher(client, "127.0.0.1:5000")
        self.assertEqual(publisher.publish("sha256:" + "b" * 64, "sub"), f"127.0.0.1:5000/ottv2-bot@{DIGEST}")
        self.assertEqual(client.images.tags, [("127.0.0.1:5000/ottv2-bot", "sub")])

    def test_accepts_aux_digest(self):
        client = FakeClient([{"aux": {"Digest": DIGEST}}])
        publisher = DockerRegistryPublisher(client, "registry.local")
        self.assertTrue(publisher.publish("id", "sub").endswith(f"@{DIGEST}"))

    def test_rejected_push_or_missing_digest_is_infrastructure_error(self):
        for records in ([{"error": "denied"}], [{"status": "Pushed"}]):
            with self.assertRaises(InfrastructureError):
                DockerRegistryPublisher(FakeClient(records), "127.0.0.1:5000").publish("id", "sub")

    def test_rejects_registry_with_scheme_or_path(self):
        with self.assertRaises(InfrastructureError):
            DockerRegistryPublisher(FakeClient([]), "http://127.0.0.1:5000/x")


if __name__ == "__main__":
    unittest.main()
