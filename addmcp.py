# /// script
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "markdownify"
# ]
# ///

from fastmcp import FastMCP
import httpx
from markdownify import markdownify

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

    # Convert HTML to markdown
    markdown_content = markdownify(response.text, heading_style="ATX")

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
