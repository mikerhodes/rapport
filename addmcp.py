# /// script
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "markdownify",
#   "beautifulsoup4"
# ]
# ///

from fastmcp import FastMCP
import httpx
from markdownify import MarkdownConverter
from bs4 import BeautifulSoup

# Create MCP server instance
server = FastMCP(name="addserver")


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


# Define the "add" function handler
@server.tool()
async def add(a: int, b: int) -> int:
    """
    Add two numbers and return the result.

    Parameters:
    a (int): First number
    b (int): Second number

    Returns:
    int: Sum of the two numbers
    """
    return a + b


@server.tool()
async def mul(a: int, b: int) -> int:
    """
    Multiply two numbers and return the result.

    Parameters:
    a (int): First number
    b (int): Second number

    Returns:
    int: Result of multiplying the two numbers
    """
    return a * b


# Run the server on default host and port (localhost:8000)
if __name__ == "__main__":
    print("Starting MCP server with 'add' function...")
    print("Server running at http://localhost:9000")
    server.run(transport="streamable-http", host="127.0.0.1", port=9000)
