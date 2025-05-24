"""
Helper script to run rapport using streamlit from within an installed
package.

    uv run rapport

Streamlit doesn't support being set up as a package entrypoint,
or consuming a package entrypoint via `streamlit run`. Therefore
we have to get a bit more creative. The primary point of creativity
is that we have to find the streamlit entrypoint python file
from within the package itself.

So we:

1. Create this file as an entrypoint (see tool.uv in pyproject.toml)
2. This file determines the path to the entrypoint, which sits next
   to it on the file system.
3. We the use runpy to execute streamlit.

When I first tried runpy I got this error:

Thread 'MainThread': missing ScriptRunContext! This warning can be ignored when running in bare mode.

This post [2] talked about "bare mode" as running during tests, or via
multiple threads, which wasn't what I was doing.

But I tweaked some things, and came up with the exec* version, and after
I readded the runpy version, it seemed work fine. Not sure what the
change was.

[1]: https://github.com/streamlit/streamlit/issues/5471#issuecomment-1341051365
[2]: https://discuss.streamlit.io/t/warning-for-missing-scriptruncontext/83893

To make this work in a package, we need to add to pyproject.toml:

[tool.uv]
package = true

[project.scripts]
rapport = "main:run_rapport"
"""

import runpy
import sys
from pathlib import Path

from rapport import appconfig, tools

tools.registry.initialise_tools(appconfig.store)


def run_with_runpy() -> None:
    p = Path(__file__).parent / "entrypoint.py"
    sys.argv = ["streamlit", "run", str(p)]
    runpy.run_module("streamlit", run_name="__main__")


if __name__ == "__main__":
    run_with_runpy()
