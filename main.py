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
# Helpers
#

def clear_chat():
    """Clears the existing chat session"""
    st.session_state["messages"] = []
    st.success('Chat cleared!', icon="✅")

def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""
    stream = ollama.chat(
        model=st.session_state["model"],
        messages=st.session_state["messages"],
        stream=True,
    )
    for chunk in stream:
        yield chunk["message"]["content"]
#
# Start rendering the app
# 

# st.title("Ollama Python Chatbot")

with st.sidebar:
    "**Ollama Python Chatbot**"
    st.button("New Chat", on_click=clear_chat)
    st.selectbox("Choose your model", models, key="model")

# Display chat messages from history on app rerun
for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Enter prompt here..."):
    # add latest message to history in format {role, content}
    st.session_state["messages"].append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking...", show_time=False):
            message = st.write_stream(stream_model_response())
        st.session_state["messages"].append({"role": "assistant", "content": message})
