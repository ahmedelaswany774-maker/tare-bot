import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RecoveryContractTests(unittest.TestCase):
    def setUp(self):
        self.story_workflow = (ROOT / ".github/workflows/story-bot.yml").read_text(encoding="utf-8")
        self.recovery_workflow = (ROOT / ".github/workflows/recover-upload.yml").read_text(encoding="utf-8")
        self.uploader = (ROOT / "story_youtube_uploader.py").read_text(encoding="utf-8")

    def test_production_artifact_contains_recovery_files(self):
        self.assertIn("name: story-${{ github.run_id }}", self.story_workflow)
        self.assertIn("story.mp4", self.story_workflow)
        self.assertIn("story_metadata.json", self.story_workflow)
        self.assertIn("upload_state.json", self.story_workflow)

    def test_recovery_downloads_matching_production_artifact(self):
        self.assertIn('gh run download "$RUN_ID" -n "story-$RUN_ID" -D recovery', self.recovery_workflow)
        self.assertNotIn('gh run download "$RUN_ID" -n story-bundle', self.recovery_workflow)

    def test_all_recovery_actions_are_sha_pinned(self):
        self.assertIn("actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683", self.recovery_workflow)
        self.assertIn("actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b", self.recovery_workflow)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", self.recovery_workflow)
        self.assertNotIn("actions/checkout@v4", self.recovery_workflow)
        self.assertNotIn("actions/setup-python@v5", self.recovery_workflow)
        self.assertNotIn("actions/upload-artifact@v4", self.recovery_workflow)

    def test_uploader_writes_recovery_state(self):
        self.assertIn('METADATA_PATH = "story_metadata.json"', self.uploader)
        self.assertIn('STATE_PATH = "upload_state.json"', self.uploader)
        self.assertIn('"status": "rendered"', self.uploader)
        self.assertIn('"status": "uploaded"', self.uploader)


if __name__ == "__main__":
    unittest.main()
