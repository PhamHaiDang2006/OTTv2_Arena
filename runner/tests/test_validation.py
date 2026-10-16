import copy
import unittest

from ottv2_runner.errors import JobValidationError
from ottv2_runner.validation import validate_build_job, validate_match_job


def match_job():
    player_blue = {
        "team": "blue-team",
        "submission_id": "00000003-0000-4000-8000-000000000001",
    }
    player_red = {
        "team": "red-team",
        "submission_id": "00000004-0000-4000-8000-000000000001",
    }
    config_players = {"BLUE": player_blue, "RED": player_red}
    return {
        "schema_version": 1,
        "job_id": "00000007-0000-4000-8000-000000000001",
        "game_id": "00000008-0000-4000-8000-000000000001",
        "attempt": 1,
        "blue_image": "registry.local/bot@sha256:" + "a" * 64,
        "red_image": "registry.local/bot@sha256:" + "b" * 64,
        "map_id": "standard",
        "engine_version": "1.0.0",
        "players": config_players,
        "config": {
            "engine_version": "1.0.0",
            "ruleset_id": "dev-v1",
            "map_id": "standard",
            "initial_fen": "9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9",
            "players": copy.deepcopy(config_players),
            "budget_ms": 60000,
            "init_ms": 10000,
            "grace_ms": 50,
            "hard_timeout_extra_ms": 1000,
            "max_turns": 300,
            "seed": 42,
        },
    }


class JobValidationTests(unittest.TestCase):
    def test_accepts_build_and_match_contract_examples(self):
        build = {
            "schema_version": 1,
            "job_id": "00000005-0000-4000-8000-000000000001",
            "submission_id": "00000003-0000-4000-8000-000000000001",
            "language": "python",
            "source_key": "submissions/00000003-0000-4000-8000-000000000001/source.zip",
            "source_sha256": "a" * 64,
            "engine_version": "1.0.0",
        }
        self.assertEqual(validate_build_job(build), build)
        self.assertEqual(validate_match_job(match_job()), match_job())

    def test_rejects_unknown_keys_and_bad_uuids(self):
        job = match_job()
        job["ignored"] = True
        with self.assertRaises(JobValidationError):
            validate_match_job(job)
        job = match_job()
        job["game_id"] = "not-a-uuid"
        with self.assertRaises(JobValidationError):
            validate_match_job(job)

    def test_rejects_cross_field_configuration_mismatch(self):
        job = match_job()
        job["config"]["engine_version"] = "1.0.1"
        with self.assertRaisesRegex(JobValidationError, "engine_version"):
            validate_match_job(job)
        job = match_job()
        job["config"]["players"]["BLUE"]["submission_id"] = "00000004-0000-4000-8000-000000000001"
        with self.assertRaisesRegex(JobValidationError, "players"):
            validate_match_job(job)

    def test_rejects_unsafe_source_key_and_non_v1_schema(self):
        build = {
            "schema_version": 2,
            "job_id": "00000005-0000-4000-8000-000000000001",
            "submission_id": "00000003-0000-4000-8000-000000000001",
            "language": "python",
            "source_key": "../source.zip",
            "source_sha256": "a" * 64,
            "engine_version": "1.0.0",
        }
        with self.assertRaises(JobValidationError):
            validate_build_job(build)


if __name__ == "__main__":
    unittest.main()
