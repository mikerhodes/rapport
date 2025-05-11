# /// script
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "markdownify",
#   "beautifulsoup4"
# ]
# ///

# A simple MCP server to demonstrate Rapport's functionality.
# It can be added to Rapport using this configuration:
# {
# "mcpdemo": {
#     "command": "uv",
#     "args": ["run", "mcpstdio.py"]
#     "allowed_tools": [
#         "download_url"
#     ]
# },
# }
# Rapport will start the server as needed.

from fastmcp import FastMCP
import httpx
from markdownify import MarkdownConverter
from bs4 import BeautifulSoup

# Create MCP server instance
server = FastMCP(name="stdiomcp")


@server.tool()
def download_url(url: str) -> str:
    """
    Download a webpage and convert its content to markdown.

    Args:
        url: The URL to download

    Returns:
        Markdown content as a string
    """
    # Fetch the webpage content
    response = httpx.get(url)
    response.raise_for_status()  # Raise an error for bad responses

    # Super-basic cleanup before passing to markdownify
    simple_unsafe_tags = [
        # Script and style tags (potential XSS risks)
        "script",
        "style",
        # Embedded content that could be problematic
        "iframe",
        "object",
        "embed",
        "applet",
        # Forms and input elements
        "form",
        "input",
        "button",
        "select",
        "textarea",
        # Potentially dangerous event handlers
        "meta",  # could contain refresh or redirect
    ]
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in simple_unsafe_tags:
        for element in soup.find_all(tag):
            element.decompose()

    # Convert HTML to markdown

    markdown_content = MarkdownConverter(heading_style="ATX").convert_soup(
        soup
    )

    return markdown_content


# Run the server on default host and port (localhost:8000)
if __name__ == "__main__":
    print("Starting MCP server...")
    server.run()
