import streamlit as st

help_content = """
Enter slash commands as your message to the model, and Rapport
will intercept the command instead of sending it to the model.

**Include text files**

- Include a single file's content into the chat:

    ```
    /include /path/to/file
    ```   

- Include several files from path using pattern glob:

    ```
    /include /path *.glob
    ```
"""

st.title("Help")
st.header("Slash commands")
st.markdown(help_content)
