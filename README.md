# Basic Ollama Streamlit app

This shows a super simple Python LLM chatbot. It uses Ollama to run LLMs locally and Streamlit to create the chatbot user interface.

![](./images/chat-screenshot.png)

Libraries:

- [ollama/ollama-python: Ollama Python library](https://github.com/ollama/ollama-python)
- [streamlit/streamlit: Streamlit — A faster way to build and share data apps.](https://github.com/streamlit/streamlit)

## Getting started

### Ollama

There are many guides on the internet for installing Ollama. But I did this:

```
curl -L \
https://github.com/ollama/ollama/releases/latest/download/ollama-darwin \
-o ollama

chmod +x ollama
```

Then it can be run with:

```
./ollama serve
```

Next download a couple of models. On a laptop with 16GB of RAM you are somewhat limited. I found the following models good, but frankly there are many to choose from:

```
ollama pull codegemma:7b
ollama pull phi4
```

The Ollama site has a list of [other available models](https://ollama.com/search)

I follow the guidance in the ollama Github README:

> [!NOTE]
> You should have at least 8 GB of RAM available to run the 7B models, 16 GB to run the 13B models, and 32 GB to run the 33B models.

### Run the python chatbot user interface

I tried out [uv](https://docs.astral.sh/uv/) in this project.

```
brew install uv
```

In this directory I ran this to add the packages:

```
uv add streamlit ollama
```

But `uv run` installs dependencies, so you should be able to just use:

```
uv run streamlit run main.py
```
