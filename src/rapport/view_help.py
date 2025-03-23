import streamlit as st

st.title("Help")

st.header("Slash commands")

st.markdown("""
Include a file's content into the chat.

```
/include /path/to/file
```   

Include several files from path using pattern glob.

```
/include /path *.glob
```
""")
