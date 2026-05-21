from pathlib import Path


class PipelineError(Exception):
    def __init__(self, message: str, stage_id: str, run_dir: Path):
        super().__init__(message)
        self.stage_id = stage_id
        self.run_dir = run_dir
