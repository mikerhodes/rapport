from io import StringIO
import random
from textwrap import dedent

import ollama
import streamlit as st

from chathistory import ChatHistoryManager

PREFERRED_MODEL = "phi4:latest"

# 
# initialize state
# 

# Initialize the chat history manager
if "history_manager" not in st.session_state:
    st.session_state["history_manager"] = ChatHistoryManager()

with open("systemprompt.md", "r") as file:
    system_prompt = file.read()
SYSTEM = {
    "role": "system",
    "content": system_prompt,
}

# Message history
if "messages" not in st.session_state:
    st.session_state["messages"] = [SYSTEM]

if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None

# Retrieve the current models from ollama
# Set a preferred model as default if there's none set
models = [model["model"] for model in ollama.list()["models"]]
if "model" not in st.session_state and PREFERRED_MODEL in models:
    st.session_state["model"] = PREFERRED_MODEL

#
# Tools
#

def tool_get_current_weather(location: str, format: str) -> str:
    """
    Get the current weather for a location (eg, a city).

    Args:
        location: a city name
        format: celcius or fahrenheit

    Returns:
        str: a string describing the weather in the location
    """
    temp = random.randint(40, 90) if format == 'fahrenheit' else random.randint(10, 25)
    return f"It's {temp} degrees {format} in {location} today."

def add_two_numbers(a: int, b: int) -> int:
  """
  Add two numbers

  Args:
    a (int): The first number
    b (int): The second number

  Returns:
    int: The sum of the two numbers
  """
  return a + b


def subtract_two_numbers(a: int, b: int) -> int:
  """
  Subtract two numbers
  """
  return a - b

available_functions = {
    "tool_get_current_weather": tool_get_current_weather,
    'add_two_numbers': add_two_numbers,
    'subtract_two_numbers': subtract_two_numbers,
}

#
# Helpers
#

def clear_chat():
    """Clears the existing chat session"""
    st.session_state["messages"] = [SYSTEM]
    st.session_state["current_chat_id"] = None
    st.success('Chat cleared!', icon="✅")

def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""

    if use_tools:
        try:
            # First allow the model to call tools we've defined.
            response = ollama.chat(
                model=st.session_state["model"],
                messages=st.session_state["messages"],
                tools=[tool_get_current_weather, add_two_numbers, subtract_two_numbers], # Actual function reference
                stream=False,
            )
            for tool in response.message.tool_calls or []:
                function_to_call = available_functions.get(tool.function.name)
                if function_to_call:
                    output = function_to_call(**tool.function.arguments)
                    print('Function output:', output)
                    st.session_state["messages"].append({'role': 'tool', 'content': str(output), 'name': tool.function.name})
                else:
                    print('Function not found:', tool.function.name)
        except:
            print("Model doesn't support tools")

        print(st.session_state["messages"])

    response = ollama.chat(
        model=st.session_state["model"],
        messages=st.session_state["messages"],
        stream=True,
    )

    for chunk in response:
        yield chunk["message"]["content"]

def generate_chat_title():
    """Generate a title from the first 6 words of the first user message"""
    # Find first user message
    user_messages = [msg for msg in st.session_state["messages"] if msg["role"] == "user"]
    if not user_messages:
        return "New Chat"
    
    # Take first 6 words of first message
    first_message = user_messages[0]["content"]
    words = first_message.split()[:6]
    title = " ".join(words)
    
    # Add ellipsis if we truncated the message
    if len(words) < len(first_message.split()):
        title += "..."
        
    return title

def save_current_chat():
    """Save the current chat session"""
    if len(st.session_state["messages"]) > 1:  # More than just system message
        title = generate_chat_title()
        chat_id = st.session_state["history_manager"].save_chat(
            st.session_state["messages"],
            title,
            st.session_state["model"],
            st.session_state["current_chat_id"]
        )
        st.session_state["current_chat_id"] = chat_id
        st.success("Chat saved successfully!", icon="✅")
    else:
        st.warning("Nothing to save - chat is empty!", icon="⚠️")

def load_chat(chat_id):
    """Load a chat from history"""
    chat = st.session_state["history_manager"].get_chat(chat_id)
    if chat:
        st.session_state["messages"] = chat["messages"]
        st.session_state["model"] = chat["model"]
        st.session_state["current_chat_id"] = chat_id

def delete_chat(chat_id):
    st.session_state["history_manager"].delete_chat(chat_id)
    if chat_id == st.session_state["current_chat_id"]:
        clear_chat()


#
# Start rendering the app
#

st.set_page_config(page_title="OllamaChat", page_icon=":robot_face:")

with st.sidebar:
    "## Configuration"
    st.selectbox("Choose your model", models, key="model")
    use_tools = st.toggle("Use tools")
    "## Ollama Python Chatbot"
    col1, col2 = st.columns(2)
    with col1:
        st.button("New Chat", on_click=clear_chat)
    with col2:
        st.button("Save Chat", on_click=save_current_chat)
    "## Summarise a file"
    uploaded_file = st.file_uploader("Upload a plain text document")
    # summarise_detail = st.pills("Level of detail", ["Brief", "Detailed"], default="Brief")
    summarise_detailed = st.toggle("Detailed summary")
    summarise_document = st.button("Go")

    # Display recent chats
    st.markdown("## Recent Chats")
    recent_chats = st.session_state["history_manager"].get_recent_chats()
    
    for chat in recent_chats:
        col1, col2 = st.columns([4, 1])
        with col1:
            # Highlight current chat
            title = chat['title']
            if chat['id'] == st.session_state["current_chat_id"]:
                title = f"📍 {title}"
            st.button(title,
                      key=f"chat_{chat['id']}",
                      on_click=load_chat,
                      args=[chat['id']])
        with col2:
            st.button("🗑️",
                      key=f"delete_{chat['id']}",
                      on_click=delete_chat,
                      args=[chat['id']])


# Display chat messages from history on app rerun
for message in st.session_state["messages"]:
    if message["role"] == "system":
        with st.expander(
            "View system prompt"
        ):
            st.markdown(message["content"])
    else:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


if summarise_document and uploaded_file is not None:
    if summarise_detailed:
        prompt = dedent("""
            1. Analyze the input text and generate 5 essential questions that, when answered, capture the main points and core meaning of the text.
            2. When formulating your questions:
                1. Address the central theme or argument
                2. Identify key supporting ideas
                3. Highlight important facts or evidence
                4. Reveal the author's purpose or perspective
                5. Explore any significant implications or conclusions.
            3. Answer all of your generated questions one-by-one in detail.\n\n""")
    else:
        prompt = "Condense the content into a bullet point summary, emphasizing the main conclusion and its immediate importance. Use a maximum of four bullet points."
    
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    string_data = stringio.read()
    user_query = {
        "role": "user",
        "content": prompt + string_data,
    }
    with st.chat_message("user"):

        summarisation_request = f"Requested summarisation of `{uploaded_file.name}` using the following prompt:\n\n {prompt}"
        st.markdown(summarisation_request)
        st.session_state["messages"].append({"role": "user", "content": summarisation_request})

    with st.chat_message("assistant"):

        def stream_summary_response(file_data):
            stream = ollama.chat(
                model=st.session_state["model"],
                messages=[
                        user_query
                ],
                stream=True,
            )
            for chunk in stream:
                yield chunk["message"]["content"]

        with st.spinner("Thinking...", show_time=False):
            message = st.write_stream(stream_summary_response(string_data))
        st.session_state["messages"].append({"role": "assistant", "content": message})

if prompt := st.chat_input("Enter prompt here..."):
    # add latest message to history in format {role, content}
    st.session_state["messages"].append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking...", show_time=False):
            # message = st.write_stream(stream_model_response())
            message = st.write_stream(stream_model_response())
        st.session_state["messages"].append({"role": "assistant", "content": message})
