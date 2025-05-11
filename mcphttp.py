# /// script
# dependencies = [
#   "fastmcp",
# ]
# ///

# A simple MCP server to demonstrate Rapport's functionality.
# It can be added to Rapport using this configuration:
# {
# "mcpdemo": {
#     "url": "http://127.0.0.1:9000/mcp/",
#     "allowed_tools": [
#         "add",
#         "mul",
#     ]
# },
# }
# Run the script using `uv run mcpdemo.py`.

from fastmcp import FastMCP

# Create MCP server instance
server = FastMCP(name="addserver")


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
    print("Starting MCP server...")
    print("Server running at http://localhost:9000")
    server.run(transport="streamable-http", host="127.0.0.1", port=9000)
