from io import StringIO
import random
from textwrap import dedent

import ollama
import streamlit as st

PREFERRED_MODEL = "phi4:latest"

# 
# initialize state
# 

# Message history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

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
    st.session_state["messages"] = []
    st.success('Chat cleared!', icon="✅")

def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""

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

#
# Start rendering the app
#
#
st.set_page_config(page_title="OllamaChat", page_icon=":robot_face:")

with st.sidebar:
    "## Configuration"
    st.selectbox("Choose your model", models, key="model")
    "## Ollama Python Chatbot"
    st.button("New Chat", on_click=clear_chat)
    "## Summarise a file"
    uploaded_file = st.file_uploader("Upload a plain text document")
    # summarise_detail = st.pills("Level of detail", ["Brief", "Detailed"], default="Brief")
    summarise_detailed = st.toggle("Detailed summary")
    summarise_document = st.button("Go")


# Display chat messages from history on app rerun
for message in st.session_state["messages"]:
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
