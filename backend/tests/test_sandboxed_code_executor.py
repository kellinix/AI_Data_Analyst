from __future__ import annotations

import pytest

from app.services.sandboxed_code_executor import (
    GeneratedCodeSandbox,
    SandboxExecutionRequest,
    SandboxUnavailableError,
    UnsafeGeneratedCodeError,
)


@pytest.mark.asyncio
async def test_generated_code_execution_fails_closed_when_disabled() -> None:
    sandbox = GeneratedCodeSandbox()
    sandbox.enabled = False
    sandbox.provider = "disabled"

    with pytest.raises(SandboxUnavailableError):
        await sandbox.execute(SandboxExecutionRequest(code="print('hello')"))


@pytest.mark.parametrize(
    "code",
    [
        "import os\nprint(os.environ)",
        "import subprocess\nsubprocess.run(['env'])",
        "exec('print(1)')",
        "eval('1 + 1')",
        "import requests\nrequests.get('https://example.com')",
        "__import__('os')",
    ],
)
def test_generated_code_validation_blocks_unsafe_capabilities(code: str) -> None:
    with pytest.raises(UnsafeGeneratedCodeError):
        GeneratedCodeSandbox.validate_code(code)


def test_generated_code_validation_allows_basic_dataframe_work() -> None:
    GeneratedCodeSandbox.validate_code(
        "import pandas as pd\n"
        "df = pd.DataFrame({'value': [1, 2, 3]})\n"
        "print(df['value'].sum())"
    )
